import boto3
import time
import webbrowser
from botocore.config import Config
from connect import connection


##| Testar se o postgres funciona:
# sudo su - postgres
# psql
# select datname from pg_database;
# \c tasks

##| Script Django:
# sudo apt-get update
# sudo apt-get install -y python3-pip
# git clone https://github.com/raulikeda/tasks.git
# cd tasks
# sudo nano ./portfolio/settings.py
# ./install.sh
# sudo ufw allow 8080/tcp -y
# sudo reboot

keyParName = "amazoncloud_key"
postgresIP = ""
AMI = ["djangoMaulemImage"]
autoScallingName = "MaulemAutoScalling"
AMIname = "MaulemAMI"
loadBalancerName = "MaulemLoadBalancer"
targetGroupName = "MaulemTarGroup"
LoadBalancerSecGroupName = "Maulem Load Balancer Security Group"



virginiaConfig       = "us-east-1"
virginiaSecGroupName = "MaulemPFvirginia"
virginiaAmi          = "ami-0279c3b3186e54acd"



ohioConfig       = "us-east-2"
ohioSecGroupName = "MaulemPFohio"
ohioAmi          = "ami-020db2c14939a8efb"


def changeRegion(newRegion = "us-east-1"):
    import os.path
    homedir = os.path.expanduser("~")
    locationConfigFile = homedir + "\\.aws\\config"

    with open(locationConfigFile, "r+") as f:
        old = f.read()
        text = ""
        
        for n in range(len(old)):
            text += old[n]
            if old[n] == "\n":
                break
            
        oldRegion = ""
        for x in range(n+10, len(old)):
            if old[x] == "\n":
                break
            oldRegion += old[x]

        writeText = text + "region = " + newRegion
        f.seek(0)
        f.write(writeText)

        return "Changed from region '{0}' to '{1}'.".format(oldRegion, newRegion)

def deleteLoadAutoscalling(region):

    loadBalancer = boto3.client("elbv2"      , region_name = region)
    autoScalling = boto3.client("autoscaling", region_name = region)

    waiterLoadBalancerCreate = loadBalancer.get_waiter('load_balancer_available')
    waiterLoadBalancerDelete = loadBalancer.get_waiter('load_balancers_deleted')

    loadBalancerList = loadBalancer.describe_load_balancers()
    for balancer in loadBalancerList['LoadBalancers']:
        if balancer["LoadBalancerName"] == loadBalancerName:

            loadBalancer.delete_load_balancer(LoadBalancerArn = balancer["LoadBalancerArn"])
            print("========================================================================")
            print("Deleting load balancer...")
            waiterLoadBalancerDelete.wait(LoadBalancerArns = [balancer["LoadBalancerArn"]])
            print("Load balancer deleted!")

    try:
        print("------------------------------------------------------------------------")
        print("Deleting auto scalling group...")
        global autoScallingName
        autoScalling.delete_auto_scaling_group(
            AutoScalingGroupName = autoScallingName,
            ForceDelete = True
        )
        print("Auto scalling group deleted!")

    except Exception as e:
        print(e)

    try:
        print("------------------------------------------------------------------------")
        print("Deleting Launch configuration...")
        autoScalling.delete_launch_configuration(LaunchConfigurationName = AMIname)
        print("Launch configuration deleted!")

    except Exception as e:
        print(e)

    return loadBalancer, autoScalling, waiterLoadBalancerCreate, waiterLoadBalancerDelete

def deleteInstances(ec2, instances, instancesNumber, securityGroupName, config):

    terminating = False

    ###| Delete old instances using our Security Group
    for n in range(instancesNumber):
        try:
            instanceSecGroup = instances['Reservations'][n]['Instances'][0]['NetworkInterfaces'][0]['Groups'][0]['GroupName']
            if instanceSecGroup == securityGroupName:
                instanceId = instances['Reservations'][n]['Instances'][0]['InstanceId']
                ec2.terminate_instances(InstanceIds = [instanceId])
                print("Terminated instance {0}.".format(instanceId))
                terminating = True
        except:
            ##| Tried to read a terminated instance Security Group but failed because terminated instances have no Security Group
            pass

    ###| Wait all instances to terminate
    while terminating:
        time.sleep(5)
        terminating = False
        instances = ec2.describe_instances()
        for n in range(instancesNumber):
            try:
                instanceSecGroup = instances['Reservations'][n]['Instances'][0]['NetworkInterfaces'][0]['Groups'][0]['GroupName']
                if instanceSecGroup == securityGroupName:
                    instanceId = instances['Reservations'][n]['Instances'][0]['InstanceId']
                    print("Still terminating instance {0} on {1}.".format(instanceId, config))
                    terminating = True
            except:
                ##| Tried to read a terminated instance Security Group but failed because terminated instances have no Security Group
                pass
        time.sleep(5)

def createInstance(config, securityGroupName, keyParName, ami):
    global postgresIP
    postgres = """
                #cloud-config
                runcmd:
                - cd /
                - sudo apt update
                - echo "Apt update done" >> /home/ubuntu/log.txt
                - sudo apt install postgresql postgresql-contrib -y
                - echo "Installed postgres" >> /home/ubuntu/log.txt
                - sudo su - postgres
                - echo "Super user created" >> /home/ubuntu/log.txt
                - sudo -u postgres psql -c "CREATE USER cloud WITH PASSWORD 'cloud';"
                - echo "User cloud created with psql" >> /home/ubuntu/log.txt
                - sudo -u postgres psql -c "CREATE DATABASE tasks;"
                - echo "Database tasks created with psql" >> /home/ubuntu/log.txt
                - sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE tasks TO cloud;"
                - echo "Granted all privileges" >> /home/ubuntu/log.txt
                - sudo echo "listen_addresses = '*'" >> /etc/postgresql/10/main/postgresql.conf
                - echo "Listeners enabled" >> /home/ubuntu/log.txt
                - sudo echo "host all all 0.0.0.0/0 trust" >> /etc/postgresql/10/main/pg_hba.conf
                - echo "Trust all all set" >> /home/ubuntu/log.txt
                - sudo ufw allow 5432/tcp -y
                - echo "Allow port 5432 on firewall" >> /home/ubuntu/log.txt
                - sudo systemctl restart postgresql
                - echo "Postgres restart" >> /home/ubuntu/log.txt
               """

    django = """
                #cloud-config
                runcmd:
                - cd /home/ubuntu 
                - sudo apt update -y
                - echo "Apt update done" >> /home/ubuntu/log.txt
                - git clone https://github.com/Maulem/tasks
                - echo "Git clone done" >> /home/ubuntu/log.txt
                - cd tasks
                - sed -i "s/node1/postgresIP/g" ./portfolio/settings.py
                - echo "Set postgres ip into node1 on settings.py" >> /home/ubuntu/log.txt
                - ./install.sh
                - echo "Installing packages" >> /home/ubuntu/log.txt
                - sudo ufw allow 8080/tcp -y
                - echo "Allow port 8080 on firewall" >> /home/ubuntu/log.txt
                - sudo reboot
                - echo "Instance reboot" >> /home/ubuntu/log.txt
               """


    ###| Initialize ec2
    ec2 = boto3.client('ec2', region_name = config)
    print("========================================================================")

    ###| Get Instances
    instances = ec2.describe_instances()
    instancesNumber = len(instances['Reservations'])
    print("Region {0} has {1} instances.".format(config, instancesNumber))

    ###| Get Security Groups
    secGroups = ec2.describe_security_groups()['SecurityGroups']
    secGroupsNumber = len(secGroups)
    print("Region {0} has {1} Security Groups.".format(config, secGroupsNumber))

    ###| Delete old AMIs
    global AMI
    oldAMIs = ec2.describe_images(Owners=["self"])
    for image in oldAMIs["Images"]:
        if image["Name"] in AMI:
            print("Deleting AMIs...")
            ec2.deregister_image(ImageId=image["ImageId"])
            print("AMIs deleted!")

    ###| Delete old instances
    deleteInstances(ec2, instances, instancesNumber, securityGroupName, config)

    ###| Get Instances
    instances = ec2.describe_instances()
    instancesNumber = len(instances['Reservations'])

    ###| Get Security Groups
    secGroups = ec2.describe_security_groups()['SecurityGroups']
    secGroupsNumber = len(secGroups)

    ###| Delete old Security Group
    for n in range(secGroupsNumber):
        if secGroups[n]["GroupName"] == securityGroupName:
            ec2.delete_security_group(GroupName = securityGroupName)
            print("Deleted Security Group {0}!".format(securityGroupName))
            break

    ###| Get VpcId
    vpcResp = ec2.describe_vpcs()
    vpcID = vpcResp["Vpcs"][0]["VpcId"]


    ###| Recreate Security Group
    createResp = ec2.create_security_group(
        GroupName = securityGroupName,
        Description = 'PF security Group',
        VpcId = vpcID
    )
    ###| Check if was all ok
    if createResp["ResponseMetadata"]["HTTPStatusCode"] == 200:
        print("Created Security Group {0}!".format(securityGroupName))
    else:
        print("Status code:" + createResp['ResponseMetadata']['HTTPStatusCode'])

    ###| Autorize ports on Security Group
    gid = createResp['GroupId']
    authResp = ec2.authorize_security_group_ingress(
        GroupId = gid,
        IpPermissions = [
            {
                'IpProtocol': 'tcp',
                'FromPort'  : 8080,
                'ToPort'    : 8080,
                'IpRanges'  : [{'CidrIp': '0.0.0.0/0'}]
            },
            {
                'IpProtocol': 'tcp',
                'FromPort'  : 5432,
                'ToPort'    : 5432,
                'IpRanges'  : [{'CidrIp': '0.0.0.0/0'}]
            },
            {
                'IpProtocol': 'tcp',
                'FromPort'  : 80,
                'ToPort'    : 80,
                'IpRanges'  : [{'CidrIp': '0.0.0.0/0'}]
            },
            {
                'IpProtocol': 'tcp',
                'FromPort'  : 22,
                'ToPort'    : 22,
                'IpRanges'  : [{'CidrIp': '0.0.0.0/0'}]
            }
        ]
    )

    ###| Check if was all ok
    if authResp['ResponseMetadata']['HTTPStatusCode'] == 200:
        print("Security Group {0} configured!".format(securityGroupName))
    else:
        print("Status code:" + authResp['ResponseMetadata']['HTTPStatusCode'])


    ###| Create a instance
    ec2_resource = boto3.resource('ec2', region_name = config)
    if config == "us-east-2":
        instance = ec2_resource.create_instances(
            ImageId = ami,
            MinCount = 1,
            MaxCount = 1,
            InstanceType = 't2.micro',
            KeyName = keyParName,
            SecurityGroups = [securityGroupName],
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [{
                    "Key": "Name",
                    "Value": "postgresMaulem"
                    }]
                }
            ],
            UserData = postgres
        )
        print("------------------------------------------------------------------------")
        print("Creating POSTGRES instance...")
        instance[0].wait_until_running()
        instance[0].reload()
        instanceID = instance[0].id
        postgresIP = instance[0].public_ip_address
        print("Created POSTGRES instance {0} on {1} with ip {2}.".format(instanceID, config, postgresIP))
        return ec2

    elif config == "us-east-1":
        django = django.replace("postgresIP", str(postgresIP))

        instance = ec2_resource.create_instances(
            ImageId = ami,
            MinCount = 1,
            MaxCount = 1,
            InstanceType = 't2.micro',
            KeyName = keyParName,
            SecurityGroups = [securityGroupName],
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [{
                    "Key": "Name",
                    "Value": "djangoMaulem"
                    }]
                }
            ],
            UserData = django
        )

        print("------------------------------------------------------------------------")
        print("Creating DJANGO Instance...")
        instance[0].wait_until_running()
        instance[0].reload()
        instanceID = instance[0].id
        djangoIP = instance[0].public_ip_address
        print("Created DJANGO instance {0} on {1} with ip {2}.".format(instanceID, config, djangoIP))

        max_time = 150 # Seconds
        seconds = 0
        print("Doing DJANGO setup:")
        while seconds < max_time:
            barLength = 50
            percent = float(seconds) * 100 / max_time
            arrow   = "=" * int(percent/100 * barLength - 1) + ">"
            spaces  = " " * (barLength - len(arrow))

            print("-Progress: [{0}{1}] {2}%".format(arrow, spaces, round(percent, 1)), end='\r')

            seconds += 1
            time.sleep(1)

        waiter = ec2.get_waiter('image_available')
        virginiaInstanceID = instanceID
        print("-Progress: [{0}{1}] {2}% ".format((barLength - 1) * "=", "=", "100"))
        print("Setup done!")

        ##| Open in chrome
        chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_path))
        webbrowser.get("chrome").open("http://" + djangoIP + ":8080/admin")

        djangoSecGroupID = gid

        return ec2, virginiaInstanceID, waiter, djangoSecGroupID
    
    else:
        instance = ec2_resource.create_instances(
            ImageId = ami,
            MinCount = 1,
            MaxCount = 1,
            InstanceType = 't2.micro',
            KeyName = keyParName,
            BlockDeviceMappings = [
                {
                    'DeviceName' : "/dev/xvda",
                    'Ebs' : {
                        'DeleteOnTermination': True,
                        'VolumeSize': 20
                    }
                }
            ],
            SecurityGroups = [securityGroupName]
        )
        
        print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        print("Creating instance...")
        instance[0].wait_until_running()
        instance[0].reload()
        instanceID = instance[0].id
        print("Created instance {0} on {1}".format(instanceID, config))
        print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")

def createAMI(ec2Virginia, instanceID, waiter):
    try:
        print("========================================================================")
        print("Creating DJANGO AMI...")

        amiImage = ec2Virginia.create_image(
            Name = AMI[0],
            InstanceId = instanceID,
            NoReboot = False,
            TagSpecifications=[{
                "ResourceType": "image",
                "Tags": [{
                    "Key": "Name",
                    "Value": "DMI"
                    }]
                }
            ]
        )

        
        waiter.wait(ImageIds=[amiImage['ImageId']])
        print("DJANGO AMI created!")

        id = amiImage['ImageId']

        return amiImage, id

    except Exception as e:
        print(e)
        return False, False

def loadBalancerSetup(ec2Virginia, ec2LoadBalancer, region, waiter):

    try:
        print("========================================================================")
        print("Creating target group...")

        targetGroups = ec2Virginia.describe_vpcs()
        targetvpcid = targetGroups["Vpcs"][0]["VpcId"]

        global targetGroupName

        targetGroupCreated = ec2LoadBalancer.create_target_group(
            Name = targetGroupName,
            Protocol = "HTTP",
            Port = 8080,
            HealthCheckEnabled = True,
            HealthCheckProtocol = "HTTP",
            HealthCheckPort = "8080",
            HealthCheckPath = "/admin/",
            Matcher = {
                "HttpCode": "200,302,301,404,403",
            },
            TargetType = "instance",
            VpcId = targetvpcid
        )

        newTargetGroup = targetGroupCreated["TargetGroups"][0]["TargetGroupArn"]


        print("Target group created")


    except Exception as e:
        print(e)

    try:
        print("------------------------------------------------------------------------")
        print("Creating Load Balancer Security Group...")

        global LoadBalancerSecGroupName

        secGroups = ec2Virginia.describe_security_groups()["SecurityGroups"]
        secGroupsNumber = len(secGroups)

        ###| Delete old Security Group
        for n in range(secGroupsNumber):
            if secGroups[n]["GroupName"] == LoadBalancerSecGroupName:
                ec2Virginia.delete_security_group(GroupName = LoadBalancerSecGroupName)
                print("Deleted Security Group {0}!".format(LoadBalancerSecGroupName))
                break

        loadBalancerConfig = Config(region_name = region)
        loadBalancerResource = boto3.resource("ec2", config = loadBalancerConfig)

        secGroupLoadBalancer = loadBalancerResource.create_security_group(
            Description = "A Security Group for Maulem load balancer",
            GroupName = LoadBalancerSecGroupName,
            TagSpecifications = [{
                    "ResourceType": "security-group",
                    "Tags": [
                        {
                            "Key": "Name",
                            "Value": "MaulemLBSG"
                        },
                    ]
                },
            ],
        )

        print("Load Balancer Security Group created!")
        
        secGroupLoadBalancer.authorize_ingress(
            CidrIp = "0.0.0.0/0",
            FromPort = 80,
            ToPort = 80,
            IpProtocol = "tcp"
        )

        secGroupLoadBalancer.load()
        print("Load Balancer Security Group configured!")


    except Exception as e:
        print(e)

    try:
        print("------------------------------------------------------------------------")
        print("Creating Load Balancer...")

        subnets = ec2Virginia.describe_subnets()
        subnetsList = []
        for subnet in subnets["Subnets"]:
            subnetsList.append(subnet["SubnetId"])

        loadBalancer = ec2LoadBalancer.create_load_balancer(
            SecurityGroups = [
                secGroupLoadBalancer.group_id
            ],
            Tags = [{
                "Key": "Name",
                "Value": "MaulemLB"
                }
            ],
            IpAddressType = "ipv4",
            Name = loadBalancerName,
            Subnets = subnetsList
        )

        loadBalancerArn = loadBalancer["LoadBalancers"][0]["LoadBalancerArn"]

        waiter.wait(LoadBalancerArns = [loadBalancerArn])
        print("Load Balancer created!")

        return newTargetGroup, loadBalancer, loadBalancerArn
    except Exception as e:
        print(e)
        return False, False, False

def launchAmi(ec2AutoScalling, AMIid, securityGroupID):
    try:
        print("========================================================================")
        print("Launching AMI...")

        global keyParName

        ec2AutoScalling.create_launch_configuration(
            LaunchConfigurationName = "MaulemAMI",
            ImageId = AMIid,
            SecurityGroups = [
                securityGroupID
                ],
            InstanceType = "t2.micro",
            KeyName = keyParName
        )
        print("AMI Launched!")

    except Exception as e:
        print(e)
  
def autoScallingSetup(ec2AutoScalling, ec2Virginia, targetGroupArn, loadBalancer, loadBalancerArn, autoScalling):
    try:

        print("========================================================================")
        print("Launching auto scalling group...")

        global autoScallingName

        zoneList = []
        zonesAvaliable = ec2Virginia.describe_availability_zones()
        for zone in zonesAvaliable["AvailabilityZones"]:
            zoneList.append(zone["ZoneName"])

        ec2AutoScalling.create_auto_scaling_group(
            AutoScalingGroupName = autoScallingName,
            LaunchConfigurationName = "MaulemAMI",
            MinSize = 1,
            MaxSize = 10,
            DesiredCapacity = 1,
            DefaultCooldown = 100,
            HealthCheckType = "EC2",
            HealthCheckGracePeriod = 60,
            TargetGroupARNs = [targetGroupArn],
            AvailabilityZones = zoneList
        )
        print("Auto scalling group created!")

    except Exception as e:
        print(e)

    try:

        print("------------------------------------------------------------------------")
        print("Creating listener...")
        loadBalancer.create_listener(
            LoadBalancerArn = loadBalancerArn,
            Protocol = "HTTP",
            Port = 80,
            DefaultActions = [
                {
                "Type": "forward",
                "TargetGroupArn": targetGroupArn
                }
            ]
        )
        print("Listener created!")
    except Exception as e:
        print(e)

    try: 
        print("------------------------------------------------------------------------")
        print("Creating policy...")

        loadBalancerName = loadBalancerArn[loadBalancerArn.find("app"):]
        targetGroupName = targetGroupArn[targetGroupArn.find("targetgroup"):]
        
        autoScalling.put_scaling_policy(
            AutoScalingGroupName = autoScallingName,
            PolicyName = "TargetTrackingScaling",
            PolicyType = "TargetTrackingScaling",
            TargetTrackingConfiguration = {
                "PredefinedMetricSpecification": {
                "PredefinedMetricType": "ALBRequestCountPerTarget",
                "ResourceLabel": f"{loadBalancerName}/{targetGroupName}"
                },
                "TargetValue": 50
            }
        )

        print("Policy created!")
    except Exception as e:
        print(e)

loadBalancer, autoScalling, waiterLoadBalancerCreate, waiterLoadBalancerDelete = deleteLoadAutoscalling(virginiaConfig)

###| Create instances first in Ohio and then in North Virginia
ec2Ohio = createInstance(ohioConfig, ohioSecGroupName, keyParName, ohioAmi)
ec2Virginia, virginiaInstanceID, waiter, djangoSecGroupID = createInstance(virginiaConfig, virginiaSecGroupName, keyParName, virginiaAmi)

###| Create an AMI from instance on North Virginia
djangoAMI, djangoAMIid  = createAMI(ec2Virginia, virginiaInstanceID, waiter)

###| Delete instance on North Virginia
instances = ec2Virginia.describe_instances()
instancesNumber = len(instances['Reservations'])
deleteInstances(ec2Virginia, instances, instancesNumber, virginiaSecGroupName, virginiaConfig)

###| Create and configure Load Balancer
targetGroupArn, createLoadBalancer, loadBalancerArn = loadBalancerSetup(ec2Virginia, loadBalancer, virginiaConfig, waiterLoadBalancerCreate)

###| Launch the AMI
launchAmi(autoScalling, djangoAMIid, djangoSecGroupID)

###| Create and configure Auto Scalling
autoScallingSetup(autoScalling, ec2Virginia, targetGroupArn, loadBalancer, loadBalancerArn, autoScalling)


print("========================================================================")
dns = createLoadBalancer["LoadBalancers"][0]["DNSName"]
print("Load balancer address: {0}".format(dns))

##| Open DNS in chrome
chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_path))
webbrowser.get("chrome").open("http://" + dns + "/admin")

##| Connects the API with the Load Balancer
connection(dns)