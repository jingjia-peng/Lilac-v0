import os
import json
import shutil
import subprocess

from utils import (
    Config,
    print_info,
    print_error,
    generate_unit_test,
    generate_incremental_tests,
)
from queryAgent import AgentResponse, AzureQueryAgent
from cloudAPImanager import AzureAPIManager

from .base import RuleExtractor


class AzureRuleExtractor(RuleExtractor):
    def __init__(self):
        self.subscription_id = Config["subscription_id"]
        if self.subscription_id is None:
            raise ValueError("Azure subscription_id not set in global-config.yml")
        super().__init__(
            query_agent=AzureQueryAgent(self.subscription_id),
            api_manager=AzureAPIManager(),
        )

    def schedule_tests(self, test_basedir="azure-test", ref_basedir="azure-ref"):
        """
        Schedule tests for Azure in following steps:
        1. read all reference terraform test files in ref_basedir
        2. for each reference file, try to generate runable unit test in test_basedir
        3. run the generated unit test
        """
        ref_files = [
            os.path.join(ref_basedir, f)
            for f in os.listdir(ref_basedir)
            if f.endswith(".tf")
        ]
        ref_files = sorted(ref_files)
        for i, ref_file in enumerate(ref_files):
            tf_type = os.path.basename(ref_file).split(".")[0]
            test_dir = os.path.join(test_basedir, tf_type)
            os.makedirs(test_dir, exist_ok=True)

            print_info(f"Generating unit test for {tf_type}")
            self.logger.warning(f"Generating unit test for {tf_type}")
            ok = generate_unit_test(
                tf_type=tf_type,
                cloud="Azure",
                ref_file_path=ref_file,
                result_dir=test_dir,
                res_cnst_msg=f"in my resource group lilac-{i}",
            )
            if not ok:
                print_error(f"Failed to generate unit test for {tf_type}")
                self.logger.error(f"Failed to generate unit test for {tf_type}")
                continue

            self.run_unit_test(test_dir)

    def run_unit_test(self, testdir: str, cleanup=True):
        test_infos = generate_incremental_tests(testdir, verbose=True)
        agent_retry = Config["query_loop_max_retry"]

        try:
            for i, (test_path, test_resource) in enumerate(test_infos):
                print_info(
                    f"Running {test_path} with resource {
                           test_resource}"
                )
                self.logger.warning(
                    f"Running {test_path} with resource {test_resource}"
                )

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
                    print_error(f"Terraform apply failed for {test_path}")
                    self.logger.error(f"Terraform apply failed for {test_path}")
                    break

                tfstate_path = os.path.join(test_path, "terraform.tfstate")
                with open(tfstate_path, "r") as f:
                    tfstate = json.load(f)

                # resource group is guaranteed to be the first resource
                if i == 0:
                    group_name = self._extract_group_name(tfstate)
                    assert (
                        group_name
                    ), "Resource group is not the first resource in testcase"
                    continue

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
                            tf_type=tf_type, target_id=target_id, group_name=group_name
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
                        continue

                    if agent_response == AgentResponse.TIMEOUT:
                        agent_retry -= 1
                        if agent_retry <= 0:
                            print_error(
                                f"Retry limit reached for {test_resource}, skip this test"
                            )
                            query_chain.dump(testdir, test_resource)
                            break
                        continue

        except Exception as e:
            print_error(f"Exception caught: {type(e).__name__} {e}")
            self.logger.error(f"Exception caught: {type(e).__name__} {e}")
        finally:
            if cleanup:
                self.cleanup(testdir, test_path)

    def _extract_group_name(self, tfstate: dict):
        for r in tfstate["resources"]:
            if r["type"] == "azurerm_resource_group":
                id = r["instances"][0]["attributes"]["id"]
                return id.split("/")[-1]
        return None
