from brain import ask


print("Акира запущен.")

while True:
    command = input("Ты: ").strip()

    if command.lower() in ["выход", "exit", "quit"]:
        print("Акира: До встречи.")
        break

    try:
        response = ask(command)
        print("Акира: " + response)

    except Exception as error:
        print("Акира: Произошла ошибка: " + str(error))
