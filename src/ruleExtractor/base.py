import os
import shutil
import logging
import subprocess


class RuleExtractor:
    def __init__(self, query_agent, api_manager):
        self.queryAgent = query_agent
        self.cloudAPImanager = api_manager
        self.cloudAPImanager.load_cleaned_api_docs()
        self.cmd_tool_dict = self.cloudAPImanager.get_cmd_dict()

        logging.basicConfig(
            level=logging.WARNING,
            handlers=[
                logging.FileHandler("train.log", "w", "utf-8"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger(__name__)
        self.tested_types = set()

        # suppress logging
        self.logger.disabled = True

    def schedule_tests(self, test_dir_list: list, cleanup=True):
        """
        Run all tests in `test_dir_list`
        """
        for test_dir in test_dir_list:
            self.run_unit_test(test_dir, cleanup)

    def run_unit_test(self, cleanup):
        """
        Run incremental test in `testdir`
        """
        raise NotImplementedError

    def cleanup(self, testdir: str, destroy_path: str):
        """
        Delete all .terraform/ .terraform.lock.hcl and .tftate in `testdir`
        """
        # destroy the resource in the last test
        subprocess.run("terraform destroy -auto-approve", cwd=destroy_path, shell=True)

        for dp, dn, fn in os.walk(testdir):
            for d in dn:
                if d == ".terraform":
                    shutil.rmtree(os.path.join(dp, d))
            for f in fn:
                if f == ".terraform.lock.hcl" or f == "terraform.tfstate":
                    os.remove(os.path.join(dp, f))
