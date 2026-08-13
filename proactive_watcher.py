import time
import hashlib
from datetime import datetime

from proactive import check_proactive


CHECK_INTERVAL = 60 * 60
last_alert = None


def get_alert_key(result):
    return hashlib.sha256(
        result.encode("utf-8")
    ).hexdigest()


print("Proactive Watcher запущен.")
print("Проверка будет выполняться раз в час.")


while True:
    try:
        result = check_proactive(3)

        if result.strip() == "NO_ACTION":
            print(
                datetime.now().strftime("%H:%M")
                + " — всё спокойно."
            )

        elif (
            "LEVEL: ATTENTION" in result
            or "LEVEL: URGENT" in result
        ):
            alert_key = get_alert_key(result)

            if alert_key != last_alert:
                print()
                print("=" * 50)
                print("АКИРА: есть повод обратить внимание")
                print()
                print(result)
                print("=" * 50)
                print()

                last_alert = alert_key
            else:
                print(
                    datetime.now().strftime("%H:%M")
                    + " — ситуация не изменилась."
                )

        else:
            print(
                datetime.now().strftime("%H:%M")
                + " — проверка завершена."
            )

    except Exception as error:
        print(
            datetime.now().strftime("%H:%M")
            + " — ошибка watcher: "
            + str(error)
        )

    time.sleep(CHECK_INTERVAL)
