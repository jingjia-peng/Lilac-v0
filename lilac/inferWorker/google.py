import os
import json
import subprocess

from utils import Config, print_info, print_cmd_result
from inferRule import (
    InferRule,
    InferAPIArg,
    GoogleIDType,
    GoogleIDSchema,
    GoogleResponseInfo,
)
from queryRule import GoogleQueryRule
from jsonpath_ng import parse

from .base import InferWorker, LiftedInstance

GOOGLE_SELFLINK_PREFIX = "https://www.googleapis.com/"


class GoogleInferWorker(InferWorker):
    def __init__(self):
        self.project = Config["google_project"]
        if not self.project:
            raise ValueError("google_project is not set in global-config.yml")
        self.region = Config["google_region"]
        if not self.region:
            raise ValueError("google_region is not set in global-config.yml")
        self.zone = Config["google_zone"]
        if not self.zone:
            raise ValueError("google_zone is not set in global-config.yml")
        super().__init__(infer_rule=InferRule(GoogleResponseInfo))

    def _print_init_lifting(self):
        print_info(f"Start lifting inference in project {self.project}...")
        self.logger.info(
            f"Start lifting inference in project {
                            self.project}..."
        )

    def prepare_infer_rules(self, query_rule_paths: list):
        for path in query_rule_paths:
            query_rule = GoogleQueryRule.load(path)
            self.infer_rule.add_query_rule(query_rule)
        print_info(self.infer_rule)
        self.logger.info(self.infer_rule)

    def _populate_top_api_queue(self, api_queue):
        print_info(
            f'Running command: gcloud asset search-all-resources --project="{
                   self.project}" --format json'
        )
        self.logger.info(
            f'Running command: gcloud asset search-all-resources --project="{self.project}" --format json'
        )
        result = subprocess.run(
            f'gcloud asset search-all-resources --project="{self.project}" --format json',
            stdout=subprocess.PIPE,
            shell=True,
            text=True,
        )
        rg_resource = json.loads(result.stdout)
        cloud_types = set()
        for resource in rg_resource:
            cloudtype = resource["assetType"]
            cloud_types.add(cloudtype)
            cloudtype_apis = self.infer_rule.get_cloudtype_apis(
                cloudtype
            )  # set of api_call
            for api in cloudtype_apis:
                if api not in api_queue:
                    api_queue.append(api)
        return cloud_types

    def _analyze_response(self, response, response_info):
        for expr, schemas in response_info.schema_map.items():
            jsonpath_expr = parse(expr)
            values = {match.value for match in jsonpath_expr.find(response)}
            cleaned_values = set()
            for value in values:
                if isinstance(value, str) and value.startswith(GOOGLE_SELFLINK_PREFIX):
                    value = value[len(GOOGLE_SELFLINK_PREFIX) :]
                    value = "/".join(value.split("/")[2:])
                    cleaned_values.add(value)
                else:
                    cleaned_values.add(str(value))
            for schema in schemas:
                if isinstance(schema, GoogleIDSchema):
                    self.tfid_map[schema].update(cleaned_values)
                elif isinstance(schema, InferAPIArg):
                    self.apiarg_map[schema].update(cleaned_values)

    def _resolve_args(self, api_queue, api, arg_names, arg_map):
        args_ready = True
        # TODO: fill in gcloud args
        return args_ready

    def _infer_tfinstance(self, tftype):
        tfid_components = self.infer_rule.get_id_components(tftype)
        # Type 1: whole ID corresponds to the TF type
        if len(tfid_components) == 1:
            assert tfid_components.pop() == "ID"
            for id in self.tfid_map[GoogleIDSchema(GoogleIDType.ID, tftype)]:
                self.lifted_instances.append(LiftedInstance(tftype, id))

        # Type 2: baseID and child components
        elif "baseID" in tfid_components:
            ids = []
            for id in self.tfid_map[GoogleIDSchema(GoogleIDType.BASE_CHILD, tftype)]:
                ids.append(id)
            child_num = len(tfid_components) - 1
            for i in range(child_num):
                child_key = self._get_child_key(i, tfid_components)
                assert (
                    child_key
                ), f"child_{
                    i} not found in tfid_components of {tftype}"
                running_ids = []
                for child in self.tfid_map[
                    GoogleIDSchema(GoogleIDType.BASE_CHILD, tftype, child_key)
                ]:
                    for id in ids:
                        running_ids.append(
                            f"{id}/{child_key[len('child_i_'):]}/{child}"
                        )
                ids = running_ids
            for id in ids:
                self.lifted_instances.append(LiftedInstance(tftype, id))

        else:
            ids = [self.project]
            comp_num = len(tfid_components)
            for i in range(comp_num):
                running_ids = []
                for comp in self.tfid_map[
                    GoogleIDSchema(GoogleIDType.COMPONENT, tftype, f"component_{i}")
                ]:
                    for id in ids:
                        running_ids.append(f"{id}/{comp}")
                ids = running_ids
            for id in ids:
                self.lifted_instances.append(LiftedInstance(tftype, id))

    def _save_instance_topo(self, path: str):
        content = f"""provider "google" {{
    project     = "{self.project}"
    region      = "{self.region}"
}}
"""
        for instance in self.import_instances:
            content += f"""
# {instance.id}
resource "{instance.tftype}" "{instance.name}" {{
    # add attributes here
}}
"""
        with open(path, "w") as f:
            f.write(content)

    def _save_instance_imported(self, output_path: str, buffer_dir="cache"):
        import_file = f"""provider "google" {{
    project     = "{self.project}"
    region      = "{self.region}"
}}
"""
        for instance in self.import_instances:
            import_file += f"""
import {{
    id = "{instance.id}"
    to = {instance.tftype}.{instance.name}
}}
"""
        with open(os.path.join(buffer_dir, "import.tf"), "w") as f:
            f.write(import_file)

        if os.path.exists(os.path.join(buffer_dir, "imported.tf")):
            os.remove(os.path.join(buffer_dir, "imported.tf"))

        print_info("Running terraform import...")
        if not os.path.exists(os.path.join(buffer_dir, ".terraform")):
            subprocess.run(
                "terraform init",
                cwd=buffer_dir,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        result = subprocess.run(
            "terraform plan -generate-config-out=imported.tf",
            cwd=buffer_dir,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        print_cmd_result(result)

        with open(os.path.join(buffer_dir, "imported.tf"), "r") as f:
            content = f.read()
        content = (
            f"""provider "google" {{
    project     = "{self.project}"
    region      = "{self.region}"
}}
"""
            + content
        )
        with open(output_path, "w") as f:
            f.write(content)

    def _get_full_api_call(self, api: str, arg_map: dict):
        # TODO: fill in gcloud command args using arg_map
        return api + " --format json"

    def _get_resource_group_response(self, response: str):
        # TODO: how to isolate a group of resource?
        return json.loads(response)
