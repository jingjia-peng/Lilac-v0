# CLI Docs Format

This directory stores cloud CLI documentation, which the pipeline references to invoke appropriate CLI commands.

## Example: Azure CLI Docs

Microsoft Azure provides a comprehensive CLI documentation repository, which we use as a reference for the format required by our pipeline. Follow the steps below to prepare the Azure CLI documentation:

1. Download the Azure CLI documentation repository:

   ```bash
   pwd # Lilac-v0/cli-docs
   git clone git@github.com:MicrosoftDocs/azure-docs-cli.git
   ```

2. Retain only the latest docs:

   ```bash
   find azure-docs-cli -mindepth 1 ! -path "azure-docs-cli/latest" ! -path "azure-docs-cli/latest/*" -exec rm -rf {} +
   mv azure-docs-cli/latest/docs-ref-autogen/* azure-cli-docs/
   rm -r azure-docs-cli
   rm azure-cli-docs/TOC.md
   ```

After completing these steps, the directory structure should resemble:

```bash
.
└── azure-docs-cli/
    ├── network/
    │   ├── vnet/
    │   │   ├── subnet.yml    # Subcommand docs: 'az network vnet subnet [operation]'
    │   │   └── ...           # Other subcommands under 'az network vnet'
    │   ├── nic/
    │   │   ├── ip-config/
    │   │   │   ├── address-pool.yml
    │   │   │   └── ...
    │   │   ├── ip-config.yml
    │   │   └── ...
    │   ├── vnet.yml          # Subcommand docs: 'az network vnet [operation]'
    │   ├── nic.yml
    │   └── ...               # Subcommands under 'az network'
    ├── vm/
    │   └── ...               # Subcommands under 'az vm'
    ├── network.yml           # Subcommand docs: 'az network [operation]'
    ├── vm.yml                # Subcommand docs: 'az vm [operation]'
    └── ...
```

At this stage, the Azure-based demo for Lilac is ready to run.

## Prepare CLI Docs for Other Cloud Providers

To use CLI docs for other cloud providers, ensure they adhere to the following format, which is compatible with our CLI doc preprocessing module.

### Command Format

Cloud CLI commands typically follow this structure:

```
[cloud-name] [top-level command group] [second-level command group] [...] [operation]
Example: az network vnet subnet list
```

### Directory Structure

The directory structure should mirror the Azure example:

```bash
.
└── cloudx-docs-cli/
    ├── top-level command group/
    │   ├── second-level/
    │   │   ├── third-level.yml  # Docs for '[cloud] [top] [second] [third] [operation]'
    │   │   └── ...              # Other subcommands under '[cloud] [top] [second]'
    │   ├── second-level.yml     # Docs for '[cloud] [top] [second] [operation]'
    │   └── ...
    ├── top-level.yml            # Docs for '[cloud] [top] [operation]'
    └── ...
```

### YAML File Structure

Each `.yml` file should include the following details for each command:

```yaml
name: az network vnet subnet
summary: Manage subnets in an Azure Virtual Network.
directCommands:
  - name: az network vnet subnet list
    summary: List the subnets in a virtual network.
    requiredParameters:
      - name: --vnet-name
        summary: The virtual network (VNet) name.
```
