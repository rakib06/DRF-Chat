from datetime import time
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.http.response import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser
from chat.models import Message, UserProfile, ClientUser
from chat.serializers import MessageSerializer, UserSerializer

# importing the requests library
import requests

# address = '10.100.14.175'
bot_address = '127.0.0.1:5001'
chat_system_address = '127.0.0.1:8000'


def index(request):
    if request.user.is_authenticated:
        return redirect('chats')
    if request.method == 'GET':
        return render(request, 'chat/index.html', {})
    if request.method == "POST":
        username, password = request.POST['username'], request.POST['password']
        user = authenticate(username=username, password=password)
        print(user)
        if user is not None:
            login(request, user)
        else:
            return HttpResponse('{"error": "User does not exist"}')
        return redirect('chats')




@csrf_exempt
def user_list(request, pk=None):
    """
    List all required messages, or create a new message.
    """
    if request.method == 'GET':
        if pk:
            users = User.objects.filter(id=pk)
        else:
            try: 
                user_id= int(User.objects.get(username=request.user.username).pk)
                user_info = ClientUser.objects.get(user_id=user_id)
           
                users = User.objects.filter(username__in=['rasa-bot', request.user.username])
            except:
                # for agent user

                users = User.objects.all()
        serializer = UserSerializer(users, many=True, context={'request': request})
        return JsonResponse(serializer.data, safe=False)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        try:
            user = User.objects.create_user(username=data['username'], password=data['password'])
            UserProfile.objects.create(user=user)
            return JsonResponse(data, status=201)
        except Exception:
            return JsonResponse({'error': "Something went wrong"}, status=400)

## Rasa part start 
  
def call_rasa(data):

    # defining a params dict for the parameters to be sent to the API
    PARAMS = {
            "sender": data["sender"],
            "message": data["message"]
        }
    # sending get request and saving the response as response object
    r = requests.post(url = bot_address, json = PARAMS)
    print("*"*100, '\n')
    print(type(r.text), r.text)
    bot_result =  eval(r.text)
    print(bot_result, type(bot_result))
    # r = [{"recipient_id":"test","text":"Can you please type your account number?"}]
    for item in bot_result:
        print(item)
        bot_data = {
            "sender": "rasa-bot",
            "receiver": item["recipient_id"],
            "message": item["text"],
            "timestamp": "1234454"
        }
        user_id = int(User.objects.get(username=item["recipient_id"]).pk)
        # chat system url
        requests.post(url = f'http://{chat_system_address}/api/messages/4/{user_id}',\
                json=bot_data)
## rasa end

# handoff
def call_human(data):
    try:
        client_data = {
                "sender": data["sender"],
                "receiver": "agent",
                "message": f'{data["sender"]} wants to talk you', 
                "timestamp": "1234454"
            }
        
        
        client_id = int(User.objects.get(username=data["sender"]).pk) # sender 
        agent_id = int(User.objects.get(username="agent").pk) # receiver 

        # chat system url
        requests.post(url = f'http://{chat_system_address}/api/messages/{agent_id}/{client_id}',\
                json=client_data)
    finally:
        notify(data, msg="FinBot: Thank you I'm transering you to an human agent!")

def notify(data, msg):
    notify_data = {
            "sender": "rasa-bot",
            "receiver": "agent",
            "message": msg,
            "timestamp": "1234454"
        }
    client_id = int(User.objects.get(username=data["sender"]).pk) # sender 
    rasa_bot_id = int(User.objects.get(username="rasa-bot").pk) # receiver 
    
    requests.post(url = f'http://{chat_system_address}/api/messages/{client_id}/{rasa_bot_id}',\
            json=notify_data)

@csrf_exempt
def message_list(request, sender=None, receiver=None):
    """
    List all required messages, or create a new message.
    """
    if request.method == 'GET':
        
        
        # client part 
        try:
            user_info = ClientUser.objects.get(user_id=sender)

            if user_info.user_id:

                messages = Message.objects.filter(
                    sender_id=sender, receiver_id__in= [user_info.connected_agent_id], is_read=False) # for robot 4
                  
                serializer = MessageSerializer(messages, many=True, context={'request': request})
                for message in messages:
                    message.is_read = True
                    message.save()
                return JsonResponse(serializer.data, safe=False)
        
        # agent part 

        except:
            try:
                user_id= int(User.objects.get(username=request.user.username).pk)
                user_info = ClientUser.objects.get(user_id=user_id)
                agent_id = user_info.connected_agent_id
                messages = Message.objects.filter(sender_id=sender, receiver_id=agent_id, is_read=False)
            except:
                messages = Message.objects.filter(sender_id=sender, receiver_id=receiver, is_read=False)
            serializer = MessageSerializer(messages, many=True, context={'request': request})
            for message in messages:
                message.is_read = True
                message.save()
            return JsonResponse(serializer.data, safe=False)

    elif request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            
            print(data)
            try:
                agent_user_id= int(User.objects.get(username=data["sender"]).pk)
                user_info = ClientUser.objects.get(connected_agent_id=agent_user_id)
                client_user_id = user_info.user_id
                print(data, "-"*100)
                data['receiver'] = User.objects.get(pk=client_user_id).username
                requests.post(url = f'http://{chat_system_address}/api/messages/\
                    {agent_user_id}/{client_user_id}',\
            json=data)
            except Exception as e: 
                print(e)
            # data = {'sender': 'sender', 'receiver': 'rasa-bot', 'message': 'HELLO'}
            serializer = MessageSerializer(data=data) 
            
            if serializer.is_valid():
                serializer.save()
                print("Mesage sent to client")
                return JsonResponse(serializer.data, status=201)
        finally:
            try:
                user_id= int(User.objects.get(username=data["sender"]).pk)
                user_info = ClientUser.objects.get(user_id=user_id)
                # check the connection type:
                if data["message"] == "bot":
                    ClientUser.objects.filter(user_id=user_info.user_id)\
                        .update(coneected_type='bot')
                    call_rasa(data)
                if user_info.connected_type == 'bot':
                    call_rasa(data)
                # call a human agent 
                elif user_info.coneected_type == 'human':
                    ClientUser.objects.filter(user_id=user_info.user_id)\
                        .update(coneected_type='human')
                    print("Calling human")
                    call_human(data)
                else:
                    pass

                # # check_the_connection_type 
                # if data["message"] == "handoff":
                #     call_human(data)
                
                # # elif data["receiver"] == 'rasa-bot':
                # #     call_rasa(data)
            except:
                print("no user found")
        return JsonResponse(serializer.errors, status=400)


def register_view(request):
    """
    Render registration template
    """
    if request.user.is_authenticated:
        return redirect('chats')
    return render(request, 'chat/register.html', {})


def chat_view(request):
    if not request.user.is_authenticated:
        return redirect('index')
    if request.method == "GET":
        return render(request, 'chat/chat.html',
                    {'users': User.objects.exclude(username=request.user.username)})


def message_view(request, sender, receiver):
    if not request.user.is_authenticated:
        return redirect('index')

    if request.method == "GET":
        try:
            user_id= int(User.objects.get(username=request.user.username).pk)
            user_info = ClientUser.objects.get(user_id=user_id)
            agent_id = user_info.connected_agent_id
            if agent_id:
                print("Y"*100)
                print(receiver)
                return render(request, "chat/messages.html",
                        {'users': User.objects.exclude(username=request.user.username),
                        'receiver': User.objects.get(id=int(agent_id)),
                         'messages': Message.objects.filter(sender_id=sender, receiver_id=receiver) |
                                   Message.objects.filter(sender_id=receiver, receiver_id=sender)})

        except:
            print("X"*100)
            return render(request, "chat/messages.html",
                      {'users': User.objects.exclude(username=request.user.username),
                       'receiver': User.objects.get(id=receiver),
                       
                        'messages': Message.objects.filter(sender_id=sender, receiver_id=receiver) |
                                    Message.objects.filter(sender_id=6, receiver_id=9) | 
                                    Message.objects.filter(sender_id=9, receiver_id=6) |
                                   Message.objects.filter(sender_id=receiver, receiver_id=sender)})

def chat_room(request, name, room):
    pass