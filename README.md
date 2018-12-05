# alexca-CarNet
Have Alexa report your VW status and send commands the CarNet App supports as well.

What you need: 
* an Alexa 
* an Alexa developer account, https://developer.amazon.com/. After registration, select Developer Console
* an AWS Console developer account, https://aws.amazon.com/. After registration, select Sign in to the Console
* a VW CarNet account
Note: use the same email of your Alexa account for the Alexa Develoepr account.

Instructions:
- Create a zip file with 'lambda_function.py' and 'modules' folder.
- Login to the AWS Developer Console and select the regions closest to you that support Alexa.
- Then select Lambda from the Services.
- Go to Functions, Create a Function, Author from scratch.
- Enter a funciton name: e.g. myCarNet, runtime: Python 2.7, Role: Create a new role from one or more templates, Role name: lambda_basic_execution, Policy templates: Simple microservice permissions.
- In Function code select Code entry type; upload a .zip file and upload file from step 1.
- Change handler to 'lambda_function.main'
- Under basic settings change time out to 1 minute, 30 seconds.
- Create two environment variables. UID for your CarNet email address, PWD for the passowrd. You can encrypt the values for intransit using the KMS service. This costs one(1) USD per month, and you must create your own key.
- Save it all and logon to the Alexa development console
- Click Create Skill, enter name: Car Net. Select Custom
- In "Interaction Model" open the skill builder and upload 'inteactionmodel.json' in the code section.

Big thanks to Strosel https://github.com/Strosel/Carnet-alexa
