import requests
import datetime

def connection(url):

    while True:
        print("")
        print("Digite o número correspondente ao método:")
        print("1 - GET")
        print("2 - POST")
        print("3 - POSTnow")
        print("4 - DELETE")
        print("5 - Exit")
        method = input("- ")

        if method == "1":

            try:
                response = requests.get("http://" + url + "/tasks/")
                print(response)
                print(response.json())
            except Exception as e:
                print(e)

        
        elif method == "2":

            try:
                ano = input("Digite o ano: ")
                mes = input("Digite o mês: ")
                dia = input("Digite o dia: ")
                hora = input("Digite a hora: ")
                minuto = input("Digite o minuto: ")
                segundo = input("Digite o segundo: ")
                date = f"{ano}-{mes}-{dia}T{hora}:{minuto}:{segundo}"

                title = input("Digite o título: ")
                description = input("Digite a descrição: ")

                request = "http://" + url + "/tasks/"

                response = requests.post(request, data = {"title": title, "pub_date": date, "description": description})

                print(request)
                print(response)
                print(response.json())

            except Exception as e:
                print(e)

        elif method == "3":

            try:
                ano = datetime.datetime.now().strftime("%Y")
                mes = datetime.datetime.now().strftime("%m")
                dia = datetime.datetime.now().strftime("%d")
                hora = datetime.datetime.now().strftime("%H")
                minuto = datetime.datetime.now().strftime("%M")
                segundo = datetime.datetime.now().strftime("%S")
                date = f"{ano}-{mes}-{dia}T{hora}:{minuto}:{segundo}"

                print("A data será configurada como: {0}".format(date))

                title = input("Digite o título: ")
                description = input("Digite a descrição: ")

                request = "http://" + url + "/tasks/"

                response = requests.post(request, data = {"title": title, "pub_date": date, "description": description})

                print(request)
                print(response)
                print(response.json())

            except Exception as e:
                print(e)

        elif method == "4":

            try:
                task_id = input("Digite o ID da tarefa: ")
                request = "http://" + url + "/tasks/"+ str(task_id) + "/"
                response = requests.delete(request)

                print(request)
                print(response)

            except Exception as e:
                print(e)

        else:
            break

if __name__ == "__main__":
    url = input("Digite a URL: ")
    connection(url)
