import json

from .base import APIArg, APIInfo, QueryRule


class AzureAPIInfo(APIInfo):
    def __init__(self, api_call: str, args: dict | list[APIArg], response: str):
        super().__init__(api_call, args, response)
        self.cloud_type = self._extract_cloud_type()

    def _extract_cloud_type(self):
        try:
            response = json.loads(self.response)
            if isinstance(response, list):
                if len(response) > 0:
                    response = response[0]
            if isinstance(response, dict):
                if "type" in response:
                    return response["type"]
        # Exceptions are caused by empty response or wrong json format in response
        except Exception:
            return None
        return None


class AzureQueryRule(QueryRule):
    def __init__(self, tftype: str, target_id: str, load=False):
        super().__init__(
            tftype=tftype,
            target_id=target_id,
            cloud_type="Azure",
            example_id="/subscriptions/1b7414a3-b034-4f7b-9708-357f1ddecd7a/resourceGroups/lilac-1-resources/providers/Microsoft.Compute/virtualMachines/lilac-1-vm",
            example_schema="/subscriptions/{{subscription_id}}/resourceGroups/{{resource_group}}/providers/Microsoft.Compute/virtualMachines/{{vm_name}}",
            load=load,
        )

    def get_query_IDschema(
        self,
        resource_group: str,
        subscription_id="1b7414a3-b034-4f7b-9708-357f1ddecd7a",
    ):
        return self.IDformat.replace("{subscription_id}", subscription_id).replace(
            "{resource_group}", resource_group
        )

    @classmethod
    def load(self, path: str):
        with open(path, "r") as f:
            data = json.load(f)
        self = AzureQueryRule(
            tftype=data["tftype"], target_id=data["targetID"], load=True
        )
        return self._load_helper(data)

    def _post_process(self):
        """
        Azure specific post processing to of ID schema.
        1. whole ID -> `ID`
        2. combined ID components -> `component_{i}`
        3. partially combined ID components -> `baseID` and `child_{i}_{comp_key}`
        """
        # extract schema of target ID
        # if we can directly extract target ID from the last response, store in IDschemas
        self._extract_id_schema("ID", self.targetID)

        # ID is not directly extractable from response, need to infer
        if "ID" not in self.IDschemas:
            # check combined ID components
            if "|" in self.targetID:
                components = self.targetID.split("|")
                # extract schema of each component
                for i in range(len(components)):
                    self._extract_id_schema(f"component_{i}", components[i])

            # check partially combined ID components
            else:
                components = self.targetID.split("/")
                # find the maximum base ID
                for i in range(len(components) // 2, 0, -1):
                    base_id = "/".join(components[: i * 2 + 1])
                    self._extract_id_schema("baseID", base_id)
                    if "baseID" in self.IDschemas:
                        break

                # find the rest components
                comp_keys, comp_vals = (
                    components[i * 2 + 1 :][::2],
                    components[i * 2 + 1 :][1::2],
                )
                for i in range(len(comp_keys)):
                    self._extract_id_schema(f"child_{i}_{comp_keys[i]}", comp_vals[i])

        # extract schema of each round arguments
        for round in range(1, len(self.api_chain)):
            for api_call_info in self.api_chain[-round]:
                for arg in api_call_info.args:
                    # check previous round response
                    for prev_api_call_info in self.api_chain[-round - 1]:
                        response = json.loads(prev_api_call_info.response)
                        schemas = self._extract_arg_schemas(arg.val, response, [])
                        if len(schemas) > 0:
                            api_call_info.add_schemas(
                                arg.name, prev_api_call_info.api_call, schemas
                            )

        self._processed = True

    def _extract_arg_schemas(
        self, arg_val: str, response, schema_list: list, prefix=""
    ):
        if isinstance(response, list):
            for i, item in enumerate(response):
                self._extract_arg_schemas(
                    arg_val, item, schema_list, prefix + "[" + str(i) + "]"
                )
        elif isinstance(response, dict):
            for k, v in response.items():
                if isinstance(v, dict) or isinstance(v, list):
                    self._extract_arg_schemas(arg_val, v, schema_list, prefix + "." + k)
                elif v == arg_val or (
                    isinstance,
                    str(v) and v.lower() == arg_val.lower(),
                ):
                    schema = prefix + "." + k
                    if schema not in schema_list:
                        schema_list.append(schema)
        elif isinstance(response, str):
            if response.lower() == arg_val.lower() and prefix not in schema_list:
                schema_list.append(prefix)
        return schema_list

    def _APIInfo(self, api_call: str, args: dict | list[APIArg], response: str):
        return AzureAPIInfo(api_call, args, response)
