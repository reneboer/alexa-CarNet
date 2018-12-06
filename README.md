# alexca-CarNet
Have Alexa report your VW status and send commands the CarNet App supports as well.

What you need: 
* an Alexa Echo, Dot or other device supporting Alexa.
* an Alexa developer account, https://developer.amazon.com/. After registration, select Developer Console
* an AWS Console developer account, https://aws.amazon.com/. After registration, select Sign in to the Console
* a VW CarNet account<br>
Note: you must use the email of your Alexa account for the Alexa Developer account (password can be different).

Instructions:
- Login to the AWS Developer Console and select the regions closest to you that support Alexa.
- Then select Lambda from the Services.
- Go to Functions, Create a Function, Author from scratch.
- Enter a funciton name: e.g. myCarNet, runtime: Python 2.7, Role: Create a new role from one or more templates, Role name: lambda_basic_execution, Policy templates: Simple microservice permissions.
- In Function code select Code entry type; upload the .zip file and upload the myCarNet.zip file.
- Change handler to `lambda_function.main`
- Under basic settings change time out to 1 minute, 30 seconds.
- Create two environment variables. `UID` for your CarNet email address, `PWD` for the passowrd. You can encrypt the values for intransit using the KMS service. This costs one(1) USD per month, and you must create your own key. AWS does store the values encrypted when the lambda is not running.
- If you want to have the parking address included you must have a Google API key. The create a third environment variable `GoogleAPIKey` to store it.
- Copy the value for ARN from the top right.
- Save it all and logon to the Alexa development console
- Click Create Skill, enter name: Car Net. Select Custom
- In "Interaction Model" open the skill builder and upload `inteactionmodel.json` in the code section.
- Save and build before moving on to the "Configuration" Section.
- Click Endpoint. Select AWS Lambda ARN. In Default region put the ARN value you took from the AWS lambda function.
- The copy the value of Your Skill ID and go back to the AWS developer console.
- Add Alexa Skills Kit as trigger to your function and paste in the Your Skill ID value. Hit Save
- Go back to the Alexa console to Text. In the Alexa Silulator enter 'open car net' and you should hear the status of your car.
- Check that you see the car net skill in the Alexa app under Your Skills, Dev.

Now you should be able to talk to your Volkswagen using Alexa.

Working on the list of commands you can use.

You can look at the Python code in the lambda_function.py. it is the same as included in the .zip file.


Big thanks to Strosel https://github.com/Strosel/Carnet-alexa
