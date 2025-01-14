from .base import CloudAPIManager


class GoogleAPIManager(CloudAPIManager):
    def __init__(self, gpt_tool_limit=128) -> None:
        super().__init__(gpt_tool_limit)

    def load_api_docs(self, dump=False):
        super().load_api_docs(
            root_dir="google-compute-cli-docs",
            filter_list=["list", "describe"],
            cmd_prefix="gcloud ",
            api_tree_file="google_compute_api_tree.yml",
            api_tree_merged_file="google_compute_api_tree_merged.yml",
            dump=dump,
        )

    def load_cleaned_api_docs(self):
        super().load_cleaned_api_docs(
            api_tree_merged_file="google_compute_api_tree_merged.yml",
            clean_dir="google-compute-cli-docs-cleaned",
            cmd_prefix="gcloud ",
        )

    def select_category_by_tftype(self, tf_type: str, retrieve_k=10, failed=[]):
        return super().select_category_by_tftype(
            tf_type=tf_type,
            tf_prefix="google_",
            cloud_type="Google",
            retrieve_k=retrieve_k,
            failed=failed,
        )


if __name__ == "__main__":
    api_manager = GoogleAPIManager()
    api_manager.load_api_docs(dump=True)
