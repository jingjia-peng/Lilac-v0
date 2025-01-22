# Lilac - Lift IaC from Clouds (WIP)

> ⚠️ Notice: This repo is under preparation for initial release. Please **don't** run the code at this point since the dependent data is not ready here.

## Setup
1. Prepare the environment
```bash
bash setup.sh
```

2. Set up AzureOpenAI API information at `config/api-config.yml` and Azure or Google cloud account information at `config/global.yml`

## Demo

### Rule extraction phase

```bash
python -m lilac --query --test-dir virtual_machine_data_disk_attachment
```

By running this command, you can see the resulting test folder structures, like

```
.
└── test/
    └── virtual_machine_data_disk_attachment/
        ├── incremental_test/
        │   ├── test_0/
        │   │   └── main.tf
        │   └── ...
        ├── main.tf
        └── *-query-chain.json
```

where the `*-query-chain.json` store the record of cloud query steps.

### Cloud lifting phase

```bash
python -m lilac --lift --rule-dir virtual_machine_data_disk_attachment --resource-group lilac-test
```

This command reads the query records generated during the rule extraction phase and transforms them into lifting rules. Then, it would try to lift all resources within the `lilac-test` resource group under your Azure account subscription.

## Customize experiments

See all options by

```bash
python -m lilac -h
```

### Extract more rules for other Azure Terraform types

1. Add your test programs under the `test` folder, with each subfolder hosting one set of resources. Please ensure that files under each subfolder can be deployed successfully. You can check this by running `terraform init && terraform plan` in the subfolders. Then run the following command

```bash
python -m lilac --query --test-dir [subdir-1] [...] [subdir-n] --cleanup
```

2. You can then use the extracted rules to lift more Azure Terraform resources that have appeared in your test programs.

```bash
python -m lilac --lift --resource-group [your-azure-resource-group]
```

### Run in other clouds

TODO
