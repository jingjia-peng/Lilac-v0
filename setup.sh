# set up environment
python -m venv env
source env/bin/activate
pip install -e .

# prepare azure cli docs
cd cli-docs
git clone git@github.com:MicrosoftDocs/azure-docs-cli.git
find azure-docs-cli -mindepth 1 ! -path "azure-docs-cli/latest" ! -path "azure-docs-cli/latest/*" -exec rm -rf {} +
mv azure-docs-cli/latest/docs-ref-autogen/* azure-cli-docs/
rm -r azure-docs-cli
rm azure-cli-docs/TOC.md

# prepare config files
cd ..
mv config/api-config-example.yml config/api-config.yml
