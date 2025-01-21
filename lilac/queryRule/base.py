import os
import json
from collections import namedtuple

from utils import Config, print_info
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

APISchema = namedtuple("APISchema", ["api_call", "schema"])


class APIArg:
    def __init__(self, arg_name: str, arg_val: str, schema_list=[]):
        self.name = arg_name
        self.val = arg_val
        self.schema_list = schema_list

    def add_schema(self, api_call: str, schema: str):
        self.schema_list.append(APISchema(api_call, schema))


class APIInfo:
    """
    Record information of a single API call.
    """

    def __init__(self, api_call: str, args: dict | list[APIArg], response: str):
        self.api_call = api_call
        if isinstance(args, dict):
            self.args = self.__init_args_schema(args)  # list of APIArg
        else:
            self.args = args
        self.response = response  # json string of cloud response

    def __init_args_schema(self, args: dict):
        schema_list = []
        for arg_name, arg_val in args.items():
            schema_list.append(APIArg(arg_name, arg_val))
        return schema_list

    def add_schemas(self, arg_name: str, prev_api: str, schema_list: list):
        for arg in self.args:
            if arg.name == arg_name:
                for schema in schema_list:
                    arg.add_schema(prev_api, schema)


class QueryRule:
    """
    Record cloud query knowledge in incremental test.
    """

    def __init__(
        self,
        tftype: str,
        target_id: str,
        cloud_type: str,
        example_id: str,
        example_schema: str,
        load=False,
    ):
        self.tftype = tftype
        self.targetID = target_id
        self.IDformat = ""
        if not load:
            self.IDformat = self.__extract_id_format(
                cloud_type, example_id, example_schema
            )
        self.IDschemas = {}
        self.api_chain = []
        self.current_round = -1
        self._processed = False

    def __extract_id_format(
        self, cloud_type: str, example_id: str, example_schema: str
    ):
        """
        Extract general schema of target ID.
        """
        agent = (
            AzureChatOpenAI(
                model=Config["model"],
                api_key=Config["api_key"],
                azure_endpoint=Config["azure_endpoint"],
                api_version=Config["api_version"],
                organization=Config["organization"],
            )
            | StrOutputParser()
        )

        messages = [
            SystemMessage(
                f"You are an useful {cloud_type} Terraform assistant. \
                You are asked to extract the ID schema of the Terraform resource.\
                Take azurerm_linux_virtual_machine for an example, \
                the ID is {example_id}, the schema should be {example_schema}. \
                The schema should be a string where the placeholders are enclosed in single curly braces. \
                Please only provide the schema string of the ID without quotes, thanks!"
            ),
            HumanMessage(
                f"Please extract schema of {
                         self.tftype} whose ID is {self.targetID}"
            ),
        ]

        response = agent.invoke(messages)
        print_info(f"{self.tftype} ID schema response: {response}")
        return response

    def reset_api_chain(self):
        self.api_chain = []
        self.current_round = -1

    def get_query_IDschema(self):
        raise NotImplementedError

    def round_update(self, api_call: str, args: dict, response: str, round: int):
        api_call_info = self.APIInfo(api_call, args, response)
        if round > self.current_round:
            self.current_round = round
            self.api_chain.append([api_call_info])
        else:
            self.api_chain[-1].append(api_call_info)

    @classmethod
    def load(self):
        raise NotImplementedError

    def load_helper(self, data):
        # load from dumped data which is post-processed
        self._processed = True

        self.IDformat = data["IDformat"]
        self.IDschemas = {}
        for comp in data["IDschema"]:
            self.IDschemas[comp["component"]] = [
                APISchema(schema["api_call"], schema["schema"])
                for schema in comp["schemas"]
            ]
        self.api_chain = []
        for round_list in data["api_chain"]:
            round_data = []
            for api_call_info in round_list:
                args = []
                for arg in api_call_info["args"]:
                    schema_list = [
                        APISchema(schema["api_call"], schema["schema"])
                        for schema in arg["schema"]
                    ]
                    args.append(APIArg(arg["name"], arg["val"], schema_list))
                api_call_info = self.APIInfo(
                    api_call_info["api_call"], args, api_call_info["response"]
                )
                round_data.append(api_call_info)
            self.api_chain.append(round_data)
        return self

    def dump(self, path: str, name: str):
        if not self._processed:
            self.post_process()
        data = {
            "tftype": self.tftype,
            "targetID": self.targetID,
            "IDformat": self.IDformat,
            "IDschema": [
                {
                    "component": comp,
                    "schemas": [
                        {"api_call": schema.api_call, "schema": schema.schema}
                        for schema in self.IDschemas[comp]
                    ],
                }
                for comp in self.IDschemas
            ],
            "api_chain": [],
        }
        for round_list in self.api_chain:
            round_data = []
            for api_call_info in round_list:
                args = []
                for arg in api_call_info.args:
                    args.append(
                        {
                            "name": arg.name,
                            "val": arg.val,
                            "schema": [
                                {"api_call": schema.api_call, "schema": schema.schema}
                                for schema in arg.schema_list
                            ],
                        }
                    )
                round_data.append(
                    {
                        "cloud_type": api_call_info.cloud_type,
                        "api_call": api_call_info.api_call,
                        "args": args,
                        "response": api_call_info.response,
                    }
                )
            data["api_chain"].append(round_data)

        with open(os.path.join(path, name + "-querychain.json"), "w") as f:
            json.dump(data, f, indent=2)

        print_info(f"Query chain of {self.tftype} dumped to {name}-querychain.json")
        print(self)

    def __str__(self) -> str:
        if not self._processed:
            self.post_process()
        ret = "===== Query Rule =====\n"
        ret += f"TF type: {self.tftype}\n"
        ret += f"Target ID: {self.targetID}\n"
        ret += f"ID format: {self.IDformat}\n"
        ret += "ID schemas:\n" if len(self.IDschemas) > 0 else ""
        for comp in self.IDschemas:
            ret += f"  {comp}:\n"
            for schema in self.IDschemas[comp]:
                ret += f"    {schema.api_call}: {schema.schema}\n"
        ret += "API chain:\n"
        for round_list in self.api_chain:
            for api_call_info in round_list:
                ret += f"  {api_call_info.api_call}: {
                    api_call_info.cloud_type if api_call_info.cloud_type else ''}\n"
                for arg in api_call_info.args:
                    ret += f"    {arg.name}: {arg.val}\n"
                    for schema in arg.schema_list:
                        ret += f"      {schema.api_call}: {schema.schema}\n"
        return ret

    def post_process(self):
        """
        Postprocessing is called when the query chain is complete.
        It extracts all possible schemas of arguments and target ID from previous response.
        """
        raise NotImplementedError

    def extract_id_schema(self, schema_key: str, target_val: str):
        """
        Helper to extract each part of the ID schema and add to IDschemas.
        """
        for round_list in self.api_chain:
            for api_call in round_list:
                schemas = self.extract_arg_schemas(
                    target_val, json.loads(api_call.response), []
                )
                for schema in schemas:
                    id_schema = APISchema(api_call.api_call, schema)
                    if schema_key not in self.IDschemas:
                        self.IDschemas[schema_key] = [id_schema]
                    elif id_schema not in self.IDschemas[schema_key]:
                        self.IDschemas[schema_key].append(id_schema)

    def extract_arg_schemas(self):
        """
        Try to extract schema of argument from response, return None if not found.
        """
        raise NotImplementedError

    def APIInfo(self):
        """
        Return the APIInfo object of the specific cloud, e.g. AzureAPIInfo, GoogleAPIInfo.
        """
        raise NotImplementedError
