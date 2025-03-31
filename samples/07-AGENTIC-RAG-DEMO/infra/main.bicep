targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resource convention')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

param chainlitExists bool

@secure()
@description('Azure OpenAI API Key')
param azureOpenAIApiKey string

@description('Azure OpenAI Endpoint')
param azureOpenAIEndpoint string

@description('Azure OpenAI API Version')
param azureOpenAIApiVersion string

@description('Azure OpenAI Chat Completion Deployed Model Name')
param azureOpenAIChatCompletionDeployedModelName string

@description('Azure Search Service Endpoint')
param azureSearchServiceEndpoint string

@secure()
@description('Azure Search Admin Key')
param azureSearchAdminKey string

@description('Azure Search Index Name')
param azureSearchIndexName string

@description('Azure SQL Server Name')
param azureSqlServerName string

@description('Azure SQL Database Name')
param azureSqlDatabaseName string

@description('Azure SQL User Name')
param azureSqlUserName string

@secure()
@description('Azure SQL Password')
param azureSqlPassword string

@description('Azure Connection String')
param azureConnectionString string

@description('Bing Connection Name')
param bingConnectionName string

@description('Id of the user or app to assign application roles')
param principalId string

// Tags that should be applied to all resources
var tags = {
  'azd-env-name': environmentName
}

// App settings for the Container App
var appSettings = [
  {
    name: 'AZURE_OPENAI_API_KEY'
    value: azureOpenAIApiKey
  }
  {
    name: 'AZURE_OPENAI_API_VERSION'
    value: azureOpenAIApiVersion
  }
  {
    name: 'AZURE_OPENAI_ENDPOINT'
    value: azureOpenAIEndpoint
  }
  {
    name: 'AZURE_OPENAI_CHAT_COMPLETION_DEPLOYED_MODEL_NAME'
    value: azureOpenAIChatCompletionDeployedModelName
  }
  {
    name: 'AZURE_SEARCH_SERVICE_ENDPOINT'
    value: azureSearchServiceEndpoint
  }
  {
    name: 'AZURE_SEARCH_ADMIN_KEY'
    value: azureSearchAdminKey
  }
  {
    name: 'AZURE_SEARCH_INDEX_NAME'
    value: azureSearchIndexName
  }
  {
    name: 'AZURE_SQL_SERVER_NAME'
    value: azureSqlServerName
  }
  {
    name: 'AZURE_SQL_DATABASE_NAME'
    value: azureSqlDatabaseName
  }
  {
    name: 'AZURE_SQL_USER_NAME'
    value: azureSqlUserName
  }
  {
    name: 'AZURE_SQL_PASSWORD'
    value: azureSqlPassword
  }
  {
    name: 'AZURE_CONNECTION_STRING'
    value: azureConnectionString
  }
  {
    name: 'BING_CONNECTION_NAME'
    value: bingConnectionName
  }
]

// Organize resources in a resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// Create a module for the Container App and other resources
module containerApp 'modules/container-app.bicep' = {
  name: 'containerApp'
  scope: rg
  params: {
    location: location
    tags: tags
    environmentName: environmentName
    appSettings: appSettings
    principalId: principalId
    chainlitExists: chainlitExists
  }
}

// Output the Container App URL
output CONTAINER_APP_URL string = containerApp.outputs.CONTAINER_APP_URL
