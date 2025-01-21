import re
from collections import namedtuple, defaultdict

from tabulate import tabulate

from lilac.queryRule import QueryRule

InferAPIArg = namedtuple("InferAPIArg", ["api_call", "arg_name"])


class ResponseInfo:
    """
    Store information that can be infered from a cloud response
    """

    def __init__(self):
        # key: general response schema in jsonpath_ng format
        # value: set of IDSchema or InferAPIArg
        self.schema_map = defaultdict(set)
        self.apiarg_schemas = set()  # set of InferAPIArg that can be infered
        self.tftypes_schemas = set()  # set of IDSchema that can be infered

    def add_id_schema(self):
        raise NotImplementedError

    def add_arg_schema(self, schema: str, api_call: str, arg_name: str):
        schema = process_schema(schema)
        self.schema_map[schema].add(InferAPIArg(api_call, arg_name))
        self.apiarg_schemas.add(InferAPIArg(api_call, arg_name))

    def __str__(self) -> str:
        return self.__str__


class InferRule:
    """
    The knowledge base that collects the global inference rules
    """

    def __init__(self, responseInfo_type):
        # key: api_call, value: ResponseInfo
        self.api_response_map = defaultdict(responseInfo_type)
        # key: cloud_type, value: set of api_call
        self.cloudtype_api_map = defaultdict(set)
        # key: api_call, value: set of relevant api_call
        # response of key api_call can be used as arguments of value api_call
        self.relevant_api_map = defaultdict(set)
        # key: api_call, value: set of arg_name
        self.api_args_map = defaultdict(set)
        # key: tftype, value: set of ID components
        self.tfid_components = defaultdict(set)

    def add_query_rule(self, query_rule: QueryRule):
        """
        Extend the inference rule knowledge base by transforming query rules
        """
        for component, schemas in query_rule.IDschemas.items():
            self.tfid_components[query_rule.tftype].add(component)
            for schema in schemas:
                self.api_response_map[schema.api_call].add_id_schema(
                    schema.schema, component, query_rule.tftype
                )

        api_call_infos = [i for round_list in query_rule.api_chain for i in round_list]
        for api_call_info in api_call_infos:
            self.cloudtype_api_map[api_call_info.cloud_type].add(api_call_info.api_call)
            for arg in api_call_info.args:
                self.api_args_map[api_call_info.api_call].add(arg.name)
                for schema in arg.schema_list:
                    self.api_response_map[schema.api_call].add_arg_schema(
                        schema.schema, api_call_info.api_call, arg.name
                    )
                    # schema-api_call response contains arguments for this api_call
                    self.relevant_api_map[schema.api_call].add(api_call_info.api_call)

    def get_id_components(self, tf_type: str) -> set:
        return self.tfid_components[tf_type]

    def get_response_info(self, api_call: str) -> ResponseInfo:
        return self.api_response_map[api_call]

    def get_cloudtype_apis(self, cloud_type: str) -> set:
        # some cloud types are not case-sensitive
        for k in self.cloudtype_api_map.keys():
            if cloud_type.lower() in k.lower():
                return self.cloudtype_api_map[k]
        return set()

    def get_relevant_apis(self, api_call: str) -> set:
        return self.relevant_api_map[api_call]

    def get_required_args(self, api_call: str) -> set:
        return self.api_args_map[api_call]

    def __str__(self) -> str:
        ret = "==========Inference Rule==========\n"

        if self.api_response_map:
            ret += "----------API Response Map----------\n"
            for api_call, response_info in self.api_response_map.items():
                ret += f"{api_call}\n{response_info}\n"

        if self.cloudtype_api_map:
            ret += "\n\n----------Cloud Type API Map----------\n"
            ret += tabulate(
                [
                    [k if k else "Unspecified", v]
                    for k, v in self.cloudtype_api_map.items()
                ],
                headers=["Cloud Type", "API Calls"],
                tablefmt="pretty",
            )

        if self.relevant_api_map:
            ret += "\n\n----------Relevant API Map----------\n"
            ret += tabulate(
                [[k, v] for k, v in self.relevant_api_map.items()],
                headers=["API Call", "Relevant API Calls"],
                tablefmt="pretty",
            )

        if self.api_args_map:
            ret += "\n\n----------API Args Map----------\n"
            ret += tabulate(
                [[k, v] for k, v in self.api_args_map.items()],
                headers=["API Call", "Required Args"],
                tablefmt="pretty",
            )
        return ret


def process_schema(schema: str) -> str:
    # process schema from specific form to general form like $[*].subnets[*].id
    return "$" + re.sub(r"\[\d+\]", "[*]", schema)
