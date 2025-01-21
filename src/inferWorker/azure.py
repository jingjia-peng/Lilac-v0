import os
import json
import subprocess

from jsonpath_ng import parse

from utils import Config, print_info, print_cmd_result
from inferRule import (
    InferRule,
    AzureIDType,
    InferAPIArg,
    AzureIDSchema,
    AzureResponseInfo,
)
from queryRule import AzureQueryRule

from .base import InferWorker, LiftedInstance


class AzureInferWorker(InferWorker):
    def __init__(self, group_name: str):
        self.subscription_id = Config["azure_subscription_id"]
        if not self.subscription_id:
            raise ValueError("azure_subscription_id is not set in global-config.yml")
        self.location = Config["azure_location"]
        if not self.location:
            raise ValueError("azure_location is not set in global-config.yml")
        self.group_name = group_name
        super().__init__(infer_rule=InferRule(AzureResponseInfo))

    def prepare_infer_rules(self, query_rule_paths: list):
        for path in query_rule_paths:
            query_rule = AzureQueryRule.load(path)
            self.infer_rule.add_query_rule(query_rule)
        print_info(self.infer_rule)
        self.logger.info(self.infer_rule)

    def _print_init_lifting(self):
        print_info(
            f"Start lifting inference in resource group {
                   self.group_name}..."
        )
        self.logger.info(
            f"Start lifting inference in resource group {
                            self.group_name}..."
        )

    def _populate_top_api_queue(self, api_queue):
        print_info(f"Running command: az resource list -g {self.group_name}")
        self.logger.info(f"Running command: az resource list -g {self.group_name}")
        result = subprocess.run(
            f"az resource list -g {self.group_name}",
            stdout=subprocess.PIPE,
            shell=True,
            text=True,
        )
        rg_resource = json.loads(result.stdout)
        cloud_types = set()
        for resource in rg_resource:
            cloudtype = resource["type"]
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
            for schema in schemas:
                if type(schema) == AzureIDSchema:
                    self.tfid_map[schema].update(values)
                elif type(schema) == InferAPIArg:
                    self.apiarg_map[schema].update(values)

    def _resolve_args(self, api_queue, api, arg_names, arg_map):
        args_ready = True
        for arg_name in arg_names:
            if arg_name == "resource-group":
                arg_map[arg_name] = self.group_name
                continue
                # if any argument is not ready, place this API back to the queue
            if InferAPIArg(api, arg_name) not in self.apiarg_map:
                args_ready = False
                break
                # add each possible value for the argument
            arg_map[arg_name] = self.apiarg_map[InferAPIArg(api, arg_name)].pop()
            # if other possible values exist, put the API back to the queue
            if self.apiarg_map[InferAPIArg(api, arg_name)]:
                api_queue.insert(0, api)
        return args_ready

    def _infer_tfinstance(self, tftype):
        tfid_components = self.infer_rule.get_id_components(tftype)
        # Type 1: whole ID corresponds to the TF type
        if len(tfid_components) == 1:
            assert tfid_components.pop() == "ID"
            for id in self.tfid_map[AzureIDSchema(AzureIDType.ID, tftype)]:
                self.lifted_instances.append(LiftedInstance(tftype, id))

        # Type 2: baseID and child components
        elif "baseID" in tfid_components:
            ids = []
            for id in self.tfid_map[AzureIDSchema(AzureIDType.BASE_CHILD, tftype)]:
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
                    AzureIDSchema(AzureIDType.BASE_CHILD, tftype, child_key)
                ]:
                    for id in ids:
                        running_ids.append(
                            f"{id}/{child_key[len('azurerm_'):]}/{child}"
                        )
                ids = running_ids
            for id in ids:
                self.lifted_instances.append(LiftedInstance(tftype, id))

        # Type 3: ID components associated by '|'
        else:
            ids = []
            comp_num = len(tfid_components)
            for i in range(comp_num):
                running_ids = []
                for comp in self.tfid_map[
                    AzureIDSchema(AzureIDType.COMPONENT, tftype, f"component_{i}")
                ]:
                    for id in ids:
                        running_ids.append(f"{id}|{comp}")
                ids = running_ids
            for id in ids:
                self.lifted_instances.append(LiftedInstance(tftype, id))

    def _save_instance_topo(self, path: str):
        content = f"""provider "azurerm" {{
    features {{}}
    subscription_id = "{self.subscription_id}"
}}

resource "azurerm_resource_group" "{self.group_name}" {{
    name     = "{self.group_name}"
    location = "{self.location}"
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
        import_file = f"""provider "azurerm" {{
    features {{}}
    subscription_id = "{self.subscription_id}"
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
            f"""provider "azurerm" {{
    features {{}}
    subscription_id = "{self.subscription_id}"
}}

resource "azurerm_resource_group" "{self.group_name}" {{
    name     = "{self.group_name}"
    location = "{self.location}"
}}
"""
            + content
        )
        with open(output_path, "w") as f:
            f.write(content)

    def _get_full_api_call(self, api: str, arg_map: dict):
        full_api = api
        for arg_name, arg_val in arg_map.items():
            full_api += f" --{arg_name} {arg_val}"
        return full_api

    def _get_resource_group_response(self, response: str):
        """
        Only return resources in this resource group
        """
        response = json.loads(response)
        rg_response = []
        if isinstance(response, list):
            for resource in response:
                if (
                    "resourceGroup" in resource
                    and resource["resourceGroup"].lower() == self.group_name.lower()
                ):
                    rg_response.append(resource)
        # TODO: handle dict type response
        return rg_response
