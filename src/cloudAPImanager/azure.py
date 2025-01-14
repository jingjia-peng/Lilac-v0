from .base import CloudAPIManager


class AzureAPIManager(CloudAPIManager):
    def __init__(self, gpt_tool_limit=128) -> None:
        super().__init__(gpt_tool_limit)

    def load_api_docs(dump=False):
        super().load_api_docs(
            root_dir="azure-cli-docs",
            filter_list=["list", "show", "get"],
            cmd_prefix="az ",
            api_tree_file="az_api_tree.yml",
            api_tree_merged_file="az_api_tree_merged.yml",
            dump=dump,
        )

    def load_cleaned_api_docs(self):
        super().load_cleaned_api_docs(
            api_tree_merged_file="az_api_tree_merged.yml",
            clean_dir="azure-cli-docs-cleaned",
            cmd_prefix="az ",
        )

    def select_category_by_tftype(self, tf_type: str, retrieve_k=10, failed=[]):
        return super().select_category_by_tftype(
            tf_type=tf_type,
            tf_prefix="azurerm_",
            cloud_type="Azure",
            retrieve_k=retrieve_k,
            failed=failed,
        )
