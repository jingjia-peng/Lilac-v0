import os

from inferWorker import AzureInferWorker
from ruleExtractor import AzureRuleExtractor

paths = []
rule_extractor = AzureRuleExtractor()
for i, path in enumerate(paths):
    print("running ", path, "...")
    rule_extractor.ablation_unit_test(path)

# dir = 'azure-test'
# paths = [
#    'virtual_machine_data_disk_attachment',
#     'cdn_frontdoor_custom_domain',
#     'cdn_frontdoor_endpoint',
#     'cdn_frontdoor_firewall_policy',
#     'cdn_frontdoor_origin',
# ]
# paths= [os.path.join(dir, p) for p in paths]

# for i, path in enumerate(paths):
#     print('running ', path, '...')
#     subprocess.run('terraform init && terraform apply -auto-approve > /dev/null', cwd=path, shell=True)
#     rule_files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.json')]
#     inferController = AzureInferWorker(subscription_id='1b7414a3-b034-4f7b-9708-357f1ddecd7a', group_name=f'lilac-{i}')
#     inferController.prepare_infer_rules(rule_files)
#     print(inferController.infer_rule)
#     inferController.lifting_inference()
#     os.makedirs(os.path.join(path, 'aztfexport'))
#     inferController.save_lifted_instances(os.path.join(path, 'aztfexport', 'lilac_lifted_instances.tf'), imported=True)
#     # have to manually delete the resources created by terraform

path = "azure-test/virtual_machine_data_disk_attachment/ablation"
rule_files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith(".json")]
inferController = AzureInferWorker(
    subscription_id="1b7414a3-b034-4f7b-9708-357f1ddecd7a", group_name="lilac-0"
)
inferController.prepare_infer_rules(rule_files)
print(inferController.infer_rule)
inferController.lifting_inference()
# os.makedirs(os.path.join(path, 'aztfexport'))
inferController.save_lifted_instances(
    os.path.join(path, "lilac_lifted_instances.tf"), imported=True
)
