from queryRule import AzureQueryRule

from .base import QueryAgent


class AzureQueryAgent(QueryAgent):
    def __init__(self, subscription_id="1b7414a3-b034-4f7b-9708-357f1ddecd7a"):
        super().__init__()
        self.subscription_id = subscription_id
        self.cloud_type = "Azure"

    def add_tools(self, cmds: list, cmd_tool_dict: dict, category: str):
        super().add_tools(cmds, cmd_tool_dict, "az " + category)

    def main_loop(self, tf_type: str, target_id: str, group_name: str):
        self.query_chain = AzureQueryRule(tf_type, target_id)
        id_schema = self.query_chain.get_query_IDschema(
            group_name, self.subscription_id
        )
        return super().main_loop(
            tf_type=tf_type,
            target_id=target_id,
            query_chain=self.query_chain,
            id_schema=id_schema,
            res_cnst_msg=f"in my resource group {group_name}",
        )

    def get_api_call_list(self, tool_calls: list):
        api_call_list = []
        raw_api_list = []
        for tool_call in tool_calls:
            cmd = self.tool_perfix + tool_call["type"].replace("_", " ")
            raw_api_list.append(cmd)
            for k, v in tool_call["args"].items():
                cmd += f" --{k} {v}"
            api_call_list.append(cmd)
        return api_call_list, raw_api_list

    def retrieve_id(self, gpt_response: dict, target_id: str):
        response_list = gpt_response["chat"].split("\n")
        for id in response_list:
            if id.lower() == target_id.lower():
                return id
        return None

    def import_content(self, tf_type: str, id: str):
        return f"""provider "azurerm" {{
    features {{}}
    subscription_id = "{self.subscription_id}"
}}
import {{
    id = "{id}"
    to = {tf_type}.example
}}
"""
