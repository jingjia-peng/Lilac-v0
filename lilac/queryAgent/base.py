import os
import subprocess
from enum import Enum

from utils import Config, print_info, print_error, print_cmd_result
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.output_parsers.openai_tools import JsonOutputToolsParser


class AgentResponse(Enum):
    SUCCESS = 0
    TIMEOUT = 1
    RESELECT = 2


class QueryAgent:
    def __init__(self):
        self.agent = AzureChatOpenAI(
            model=Config["model"],
            api_key=Config["api_key"],
            azure_endpoint=Config["azure_endpoint"],
            api_version=Config["api_version"],
            organization=Config["organization"],
        ) | {
            "AIMessage": lambda x: x,
            "tool_calls": JsonOutputToolsParser(return_id=True),
            "chat": StrOutputParser(),
        }

        self.tools = []
        self.tool_perfix = (
            ""  # used to truncate the tool name to obey GPT tool name length limit
        )
        self.messages = []

    def reset(self):
        """
        Reset before starting a new main loop.
        """
        self.tools = []
        self.tool_perfix = ""
        self.messages = []

    def add_tools(self, cmds: list, cmd_tool_dict: dict, tool_perfix: str):
        """
        @param cmds: list of command names, return of `cloudAPImanager.get_cmd_by_category(category)`
        @param cmd_tool_dict: dict of command name to tool definitions, return of `cloudAPImanager.get_cmd_dict()`
        """
        self.tool_perfix = tool_perfix
        for cmd in cmds:
            cmd_info = cmd_tool_dict[cmd]
            tool_info = {
                "type": "function",
                "function": {
                    "name": cmd_info["name"][len(tool_perfix) :].replace(" ", "_"),
                    "description": cmd_info["summary"],
                    "requiredParameters": [],
                },
                "required": [],
                "additionalProperties": False,
            }
            if "requiredParameters" in cmd_info:
                for req_arg in cmd_info["requiredParameters"]:
                    tool_info["function"]["requiredParameters"].append(
                        {
                            "name": req_arg,
                            "description": cmd_info["requiredParameters"][req_arg][
                                "summary"
                            ],
                        }
                    )
                    tool_info["required"].append(req_arg)
            self.tools.append(tool_info)

    def main_loop(
        self,
        tf_type: str,
        target_id: str,
        query_chain,
        id_schema: str,
        res_cnst_msg: str,
    ):
        if not self.tools:
            print_error("No tools added to the agent.")
            return AgentResponse.RESELECT, query_chain

        self.query_chain = query_chain
        IDschema = id_schema
        self.messages = self.__get_init_msg(tf_type, res_cnst_msg, IDschema)

        for i in range(Config["query_loop_max_iter"]):
            print_info(f"########## Round {i+1} ##########")
            gpt_response = self.agent.invoke(self.messages, tools=self.tools)
            self.__print_gpt_response(gpt_response)
            self.messages.append(gpt_response["AIMessage"])

            # continue querying the cloud
            if gpt_response["tool_calls"]:
                self.run_cloud_query(gpt_response=gpt_response, round=i)

            # ask external API manager to reselect the API group and restart the loop
            elif "reselect" in gpt_response["chat"]:
                self.query_chain.reset_api_chain()
                return AgentResponse.RESELECT, self.query_chain

            # validate the retrieved ID
            else:
                retrieved_id = self.retrieve_id(
                    gpt_response=gpt_response, target_id=target_id
                )

                # response is not in the correct format
                if not retrieved_id:
                    self.messages.append(self.__get_regen_id_msg())

                # validate the IDs
                elif self.__validate_id(tf_type=tf_type, id=retrieved_id):
                    return AgentResponse.SUCCESS, self.query_chain

        self.query_chain.reset_api_chain()
        return AgentResponse.TIMEOUT, self.query_chain

    def run_cloud_query(self, gpt_response: dict, round: int):
        """
        Run the cloud query commands given by `gpt_response`.
        Append the cloud responses in self.messages as the tool call responses.
        """
        cloud_api_call_list, raw_api_list = self.get_api_call_list(
            gpt_response["tool_calls"]
        )
        failed_api = []
        for i, cloud_api_call in enumerate(cloud_api_call_list):
            print_info(f"Running command: {cloud_api_call}")
            try:
                result = subprocess.run(
                    cloud_api_call,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.TimeoutExpired:
                result = subprocess.CompletedProcess(
                    args=cloud_api_call,
                    returncode=1,
                    stdout="",
                    stderr="Command timeout",
                )

            success = result.returncode == 0
            cloud_response = result.stdout if success else result.stderr
            # truncate the message to avoid exceeding limit
            cloud_response = (
                cloud_response[: Config["GPT_MSG_MAXLEN"]]
                if len(cloud_response) > Config["GPT_MSG_MAXLEN"]
                else cloud_response
            )
            print_info("Cloud response:")
            print(cloud_response)

            api_response_message = ToolMessage(
                content=cloud_response,
                tool_call_id=gpt_response["tool_calls"][i]["id"],
                status="success" if success else "error",
            )
            self.messages.append(api_response_message)

            # don't update the query chain if the command returns empty
            if success and cloud_response != "[]\n":
                print_info("Updating query chain...")
                self.query_chain.round_update(
                    raw_api_list[i],
                    gpt_response["tool_calls"][i]["args"],
                    cloud_response,
                    round,
                )
            elif "the following arguments are required" in cloud_response:
                failed_api.append(i)

        for i in failed_api:
            self.messages.append(
                self.__get_argerr_msg(gpt_response["tool_calls"][i]["type"])
            )

    def retrieve_id(self, gpt_response: dict, target_id: str):
        raise NotImplementedError

    def __validate_id(self, tf_type: str, id: str, path="cache"):
        """
        Validate the IDs by importing the resources in Terraform.
        If failed, append the error message in self.messages.
        """
        self.__gen_import_tffile(tf_type=tf_type, id=id, path=path)
        import_err = self.__run_tfimport(path)
        if not import_err:
            return True
        import_err_msg = {"role": "user", "content": import_err}
        self.messages.append(import_err_msg)
        return False

    def __gen_import_tffile(self, tf_type: str, id: str, path="cache"):
        # remove previous import test files
        (
            os.remove(os.path.join(path, "imported.tf"))
            if os.path.exists(os.path.join(path, "imported.tf"))
            else None
        )
        (
            os.remove(os.path.join(path, "import.tf"))
            if os.path.exists(os.path.join(path, "import.tf"))
            else None
        )

        file = self.import_content(tf_type, id)
        with open(os.path.join(path, "import.tf"), "w") as f:
            f.write(file)

    def import_content(self, tf_type: str, id: str):
        """
        Return the cloud-specific Terraform import content.
        Should include the provider block and import block.
        """
        raise NotImplementedError

    def __run_tfimport(self, path="cache"):
        print_info("Running terraform import test")
        if not os.path.exists(os.path.join(path, ".terraform")):
            subprocess.run(
                "terraform init",
                cwd=path,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        result = subprocess.run(
            "terraform plan -generate-config-out=imported.tf",
            cwd=path,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        print_cmd_result(result)

        # import may return error if imported block is not syntatically correct, but it still prove the IDs are valid
        if (
            result.returncode != 0
            and "Config generation is experimental" not in result.stdout
        ):
            return result.stderr
        return None

    def __print_gpt_response(self, response: dict):
        print_info("Chat response:")
        print(response["chat"]) if response["chat"] else None
        api_call_list, _ = self.get_api_call_list(response["tool_calls"])
        for api_call in api_call_list:
            print("API call:", api_call)

    def get_api_call_list(self, tool_calls: list):
        """
        Construct the full API call list from the tool calls.
        @return: list of full API calls, list of raw API calls without arguments.
        """
        raise NotImplementedError

    def __get_init_msg(self, tf_type: str, res_cnst_msg: str, IDschema: str):
        """
        @param res_cnst_msg: message to describe the resource constraint in cloud query.
        E.g. 'in my resource group {group_name}' for Azure;
        'in my project {project_name} in zone {zone}' for GCP.
        """
        return [
            SystemMessage(
                f'You are a helpful {self.cloud_type} Cloud customer support assistant. \
            Your customer is asking to query cloud resource IDs corresponding to Terraform resource types, \
            so they can use those ID for `terraform import`. \
            In your response, please choose one of the following actions:\
            1. Give the next {self.cloud_type} command to query {tf_type} based on previous tool response, \
                return command with all required arguments via tool_calls and nothing in chat.\
            2. List the IDs of all \'{tf_type}\' strictly following the format "<ID>\\n" in chat and nothing in tool_calls.\
            3. If the IDs are not in the correct format, please provide them correctly in chat and nothing in tool_calls.\
            4. If no suitable command are found in tools, please return only "reselect" in chat and nothing in tool_calls.'
            ),
            HumanMessage(
                f"I want to query the IDs of all '{tf_type}' {res_cnst_msg}. \
                The ID schema is {IDschema}. Notice that sometimes IDs don't directly appear in API response, \
                but you can infer them according to the ID schema. \
                Please give me a chain of step by step {self.cloud_type} CLI commands to do so."
            ),
        ]

    def __get_regen_id_msg(self):
        return HumanMessage(
            content="Your retrieved IDs are not in the correct format. \
            Please provide the IDs correctly strictly following the format <ID>\\n."
        )

    def __get_argerr_msg(self, tool_name: str):
        req_args = []
        for tool in self.tools:
            if tool["function"]["name"] == tool_name:
                req_args.append(tool["function"]["requiredParameters"])
        return HumanMessage(
            content=f"The arguments of the command are not correct, please whether correctly fill in those required arguments \
                {req_args}, or generate other cloud API query to obtained data for those arguments."
        )
