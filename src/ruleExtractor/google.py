import os
import json
import shutil
import subprocess

from utils import Config, print_info, print_error, generate_incremental_tests
from queryAgent import AgentResponse, GoogleQueryAgent
from cloudAPImanager import GoogleAPIManager

from .base import RuleExtractor


class GoogleRuleExtractor(RuleExtractor):
    def __init__(self):
        super().__init__(
            query_agent=GoogleQueryAgent(),
            api_manager=GoogleAPIManager(),
        )

    def run_unit_test(self, testdir: str, cleanup):
        """
        Run incremental test in `testdir`
        """
        test_infos = generate_incremental_tests(testdir, verbose=True)
        agent_retry = Config["query_loop_max_retry"]

        try:
            for i, (test_path, test_resource) in enumerate(test_infos):
                print_info(
                    f"Running {test_path} with resource {
                           test_resource}"
                )
                self.logger.info(f"Running {test_path} with resource {test_resource}")

                # prepare terraform environment
                if i == 0:
                    shutil.move(
                        os.path.join(testdir, ".terraform.lock.hcl"),
                        os.path.join(test_path, ".terraform.lock.hcl"),
                    )
                    shutil.move(
                        os.path.join(testdir, ".terraform"),
                        os.path.join(test_path, ".terraform"),
                    )
                else:
                    shutil.move(
                        os.path.join(test_infos[i - 1][0], "terraform.tfstate"),
                        os.path.join(test_path, "terraform.tfstate"),
                    )
                    shutil.move(
                        os.path.join(test_infos[i - 1][0], ".terraform.lock.hcl"),
                        os.path.join(test_path, ".terraform.lock.hcl"),
                    )
                    shutil.move(
                        os.path.join(test_infos[i - 1][0], ".terraform"),
                        os.path.join(test_path, ".terraform"),
                    )

                try:
                    subprocess.run(
                        "terraform apply -auto-approve", cwd=test_path, shell=True
                    )
                except subprocess.CalledProcessError:
                    print_error("Terraform apply failed for", test_path)
                    self.logger.error(f"Terraform apply failed for {test_path}")
                    break

                tfstate_path = os.path.join(test_path, "terraform.tfstate")
                with open(tfstate_path, "r") as f:
                    tfstate = json.load(f)

                tf_type = test_resource.split(".")[0]
                tf_name = test_resource.split(".")[1]
                target_id = None
                for r in tfstate["resources"]:
                    if r["type"] == tf_type and r["name"] == tf_name:
                        target_id = r["instances"][0]["attributes"]["id"]
                        break
                assert target_id, "Target resource not found in tfstate"

                # AI agent main loop to collect query chain
                failed_category = []
                while True:
                    self.queryAgent.reset()
                    category = self.cloudAPImanager.select_category_by_tftype(
                        tf_type, failed=failed_category
                    )
                    cmds = self.cloudAPImanager.get_cmd_by_category(category)
                    self.queryAgent.add_tools(cmds, self.cmd_tool_dict, category)

                    try:
                        agent_response, query_chain = self.queryAgent.main_loop(
                            tf_type=tf_type, target_id=target_id
                        )
                    except Exception as e:
                        print_error(
                            f"Exception caught in queryAgent main_loop: {
                                          type(e).__name__} {e}"
                        )
                        self.logger.error(
                            f"Exception caught in queryAgent main_loop: {
                                          type(e).__name__} {e}"
                        )
                        break

                    if agent_response == AgentResponse.SUCCESS:
                        print_info(agent_response)
                        query_chain.dump(testdir, test_resource)
                        self.tested_types.add(tf_type)
                        break

                    print_error(agent_response)
                    if agent_response == AgentResponse.RESELECT:
                        failed_category.append(category)
                        if (
                            len(failed_category)
                            == Config["select_cli_category_retrieve_k"]
                        ):
                            print_error(
                                f"No suitable category found for {test_resource}, skip this test",
                            )
                            query_chain.dump(testdir, test_resource)
                            break

                    if agent_response == AgentResponse.TIMEOUT:
                        agent_retry -= 1
                        if agent_retry == 0:
                            print_error(
                                f"Retry limit reached for {test_resource}, skip this test"
                            )
                            query_chain.dump(testdir, test_resource)
                            break

        except Exception as e:
            print_error(f"Exception caught: {type(e).__name__} {e}")
            self.logger.error(f"Exception caught: {type(e).__name__} {e}")
        finally:
            if cleanup:
                self.cleanup(testdir, test_path)
