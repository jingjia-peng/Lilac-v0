import os

import yaml

# TODO: set the path to the config file, e.g. "api-config-example.yml"
api_config_path = os.path.join("config", "api-config.yml")

with open(api_config_path, "r") as f:
    api_config = yaml.safe_load(f)

with open(os.path.join("config", "global-config.yml"), "r") as f:
    global_config = yaml.safe_load(f)

Config = {
    # AzureChatOpenAI for agent
    "model": api_config["model"],
    "api_version": api_config["api_version"],
    "api_key": api_config["api_key"],
    "azure_endpoint": api_config["azure_endpoint"],
    "organization": api_config["organization"],
    # pipeline parameters
    "GPT_MSG_MAXLEN": global_config["GPT_MSG_MAXLEN"],
    "GPT_TOOL_LIMIT": global_config["GPT_TOOL_LIMIT"],
    "select_cli_category_retrieve_k": global_config["select_cli_category_retrieve_k"],
    "query_loop_max_iter": global_config["query_loop_max_iter"],
    "query_loop_max_retry": global_config["query_loop_max_retry"],
    # Azure cloud test parameters
    "azure_subscription_id": (
        global_config["azure_subscription_id"]
        if "azure_subscription_id" in global_config
        else None
    ),
    "azure_location": (
        global_config["azure_location"] if "azure_location" in global_config else None
    ),
    # google cloud test parameters
    "google_project": (
        global_config["google_project"] if "google_project" in global_config else None
    ),
    "google_region": (
        global_config["google_region"] if "google_region" in global_config else None
    ),
    "google_zone": (
        global_config["google_zone"] if "google_zone" in global_config else None
    ),
}
