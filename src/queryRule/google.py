import json

from .base import APIArg, APIInfo, QueryRule

GOOGLE_SELFLINK_PREFIX = "https://www.googleapis.com/"


class GoogleAPIInfo(APIInfo):
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
                if "kind" in response:
                    # "compute#firewallPolicy" -> "compute.googleapis.com/FirewallPolicy"
                    kind = response["kind"]
                    kind_parts = kind.split("#")
                    if len(kind_parts) == 2:
                        return f"{kind_parts[0]}.googleapis.com/{kind_parts[1].capitalize()}"
        # Exceptions are caused by empty response or wrong json format in response
        except Exception:
            pass
        return None


class GoogleQueryRule(QueryRule):
    def __init__(self, tftype: str, target_id: str, load=False):
        super().__init__(
            tftype=tftype,
            target_id=target_id,
            cloud_type="Google",
            example_id="'projects/iac-lifting-test/global/firewallPolicies/my-policy/associations/my-association' and 'primary-network/primary-peering'",
            example_schema="'projects/{{project}}/global/firewallPolicies/{{firewall_policy_name}}/associations/{{association_name}}' and \
                '{{project}}/{{network_name}}/{{peering_name}}'(need to add {{project}} to those ids without a project ID in the path)",
            load=load,
        )

    def get_query_IDschema(self, project: str):
        return self.IDformat.replace("{project}", project)

    @classmethod
    def load(self, path: str):
        with open(path, "r") as f:
            data = json.load(f)
        self = GoogleQueryRule(
            tftype=data["tftype"], target_id=data["targetID"], load=True
        )
        return self._load_helper(data)

    def _post_process(self):
        """
        Google specific post processing to of ID schema.
        1. whole ID -> `ID`
        2. base ID components -> `baseID`, `child_{i}_{component}`
        3. combined ID -> 'component_{i}
        """
        # extract schema of target ID
        # if we can directly extract target ID from the last response, store in IDschemas
        self._extract_id_schema("ID", self.targetID)

        # ID is not directly extractable from response, need to infer
        if "ID" not in self.IDschemas:
            # check combined ID components
            if not self.targetID.startswith("projects/"):
                components = self.targetID.split("/")
                for i in range(len(components)):
                    self._extract_id_schema(f"component_{i}", components[i])

            # check partially combined ID components
            else:
                components = self.targetID.split("/")
                # find the maximum base ID
                for i in range(len(components) // 2, 0, -1):
                    # projects/iac-lifting-test/global/
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
                elif self._is_match(v, arg_val):
                    schema = prefix + "." + k
                    if schema not in schema_list:
                        schema_list.append(schema)
        elif self._is_match(response, arg_val) and prefix not in schema_list:
            schema_list.append(prefix)
        return schema_list

    def _is_match(self, v, arg_val: str) -> bool:
        if isinstance(v, str) and v.startswith(GOOGLE_SELFLINK_PREFIX):
            v_id = "/".join(v[len(GOOGLE_SELFLINK_PREFIX) :].split("/")[2:])
            if v_id == arg_val:
                return True
        else:
            if str(v) == str(arg_val):
                return True
        return False

    def _APIInfo(self, api_call: str, args: dict | list[APIArg], response: str):
        return GoogleAPIInfo(api_call, args, response)
