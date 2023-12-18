import mysql.connector
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from datetime import datetime, timedelta
import time
import socket
import serial
import threading

db_params = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "4pcex2twa",
    "database": "MonitoringSystem"
}


data = {}
ser = serial.Serial('COM3', 115200, timeout=1)
def plot_sensor_data(table_names, time_period_hours=1):
    mydb = mysql.connector.connect(**db_params)

    mycursor = mydb.cursor()

    plt.figure(figsize=(10, 6))

    max_decimal_places = 2

    for table_name in table_names:
        start_time = datetime.now() - timedelta(hours=time_period_hours)

        query = f"SELECT Timestamp, Value FROM {table_name} WHERE Timestamp >= %s ORDER BY Timestamp"
        mycursor.execute(query, (start_time,))
        results = mycursor.fetchall()

        timestamps, values = zip(*results)

        data[table_name] = {"timestamps": timestamps, "values": values}

        max_decimal_places = max(
            max_decimal_places,
            max(
                map(lambda x: len(str(x).split(".")[1]) if "." in str(x) else 0, values),
                default=0
            )
        )
        plt.plot(timestamps, values, label=table_name)

    plt.title(f"Dane z różnych tabel (Ostatnie {time_period_hours} godzin)")
    plt.xlabel('Czas')
    plt.ylabel('Wartość')
    plt.legend()

    plt.yticks(plt.yticks()[0], [f"{tick:.{max_decimal_places}f}" for tick in plt.yticks()[0]])

    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.minorticks_on()
    plt.show()

    mydb.close()



def update_plot(i):
    global data

    mydb = mysql.connector.connect(**db_params)

    mycursor = mydb.cursor()

    max_decimal_places = 2

    for table_name in data:
        if table_name in selected_tables:
            query = f"SELECT Timestamp, Value FROM {table_name} WHERE Timestamp >= %s ORDER BY Timestamp DESC LIMIT 1"
            mycursor.execute(query, (
                data[table_name]["timestamps"][-1] if data[table_name]["timestamps"] else datetime.now() - timedelta(
                    hours=1),))
            result = mycursor.fetchone()

            if result:
                timestamp, value = result
                data[table_name]["timestamps"] = data[table_name]["timestamps"] + (timestamp,)
                data[table_name]["values"] = data[table_name]["values"] + (value,)
                max_decimal_places = max(
                    max_decimal_places,
                    len(str(value).split(".")[1]) if "." in str(value) else 0
                )

    plt.clf()
    for table_name in data:
        if table_name in selected_tables:
            plt.plot(data[table_name]["timestamps"], data[table_name]["values"], label=table_name)

    plt.title("Dynamiczny wykres z różnych tabel")
    plt.xlabel("Czas")
    plt.ylabel("Wartość")
    plt.legend()

    plt.yticks(plt.yticks()[0], [f"{tick:.{max_decimal_places}f}" for tick in plt.yticks()[0]])

    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.minorticks_on()
    plt.show()

    mydb.close()

def import_plant_data(plant_id):
    try:
        mydb = mysql.connector.connect(**db_params)
        mycursor = mydb.cursor()

        query = """
            INSERT INTO CurrentPlants (plant_id, plant_name, current_temperature, current_humidity_air, current_humidity_soil, current_lighting)
            SELECT plant_id, plant_name, required_temperature, required_humidity_air, required_humidity_soil, required_lighting
            FROM Plants
            WHERE plant_id = %s;
        """
        mycursor.execute(query, (plant_id,))

        mydb.commit()
        print(f'Dane o roślinie o ID {plant_id} zostały zaimportowane do tabeli CurrentPlants.')

    except mysql.connector.Error as err:
        print(f'Błąd: {err}')

    finally:
        if mydb.is_connected():
            mycursor.close()
            mydb.close()


def delete_plant(plant_id, num_plants_to_delete):
    try:
        mydb = mysql.connector.connect(**db_params)
        mycursor = mydb.cursor()

        query_count = "SELECT COUNT(*) FROM CurrentPlants WHERE plant_id = %s"
        mycursor.execute(query_count, (plant_id,))
        count_result = mycursor.fetchone()

        if count_result and count_result[0] >= num_plants_to_delete:
            query_delete = "DELETE FROM CurrentPlants WHERE plant_id = %s LIMIT %s"
            mycursor.execute(query_delete, (plant_id, num_plants_to_delete))
            mydb.commit()
            print(f'{num_plants_to_delete} roślin(y) o ID {plant_id} zostało(usunięte) z tabeli CurrentPlants.')
        else:
            print(f'Nie istnieje wystarczająca ilość roślin o ID {plant_id} do usunięcia. Aktualna ilość: {count_result[0]}.')

    except mysql.connector.Error as err:
        print(f'Błąd: {err}')

    finally:
        if mydb.is_connected():
            mycursor.close()
            mydb.close()

def calculate_and_insert_average():
    try:
        mydb = mysql.connector.connect(**db_params)
        mycursor = mydb.cursor()

        if not ser.is_open:
            ser.open()

        columns = ["current_temperature", "current_humidity_air", "current_humidity_soil", "current_lighting"]
        tables = ["currentvalue_temperatura", "currentvalue_wilgotnoscpowietrza", "currentvalue_wilgotnoscgleby", "currentvalue_natezenieswiatla"]

        for column, table in zip(columns, tables):
            query = f"SELECT AVG({column}) FROM CurrentPlants"
            mycursor.execute(query)
            result = mycursor.fetchone()
            average_value = result[0]
            average_value_rounded = round(average_value, 2)
            insert_query = f"INSERT INTO {table} (timestamp, set_value) VALUES (%s, %s)"
            mycursor.execute(insert_query, (datetime.now(), average_value))
            mydb.commit()

            data_to_send = f"{table}:{average_value}"

            if ser.is_open:
                ser.write(data_to_send.encode())
                print(f"Wartość {column}: {average_value_rounded} została wysłana do Arduino.")
                time.sleep(5)
            else:
                print("Błąd: Port szeregowy nie jest otwarty!")

    except mysql.connector.Error as err:
        print(f'Błąd: {err}')

    finally:
        if mydb.is_connected():
            mycursor.close()
            mydb.close()

        ser.close()



def receive_sensor_data_thread():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 5678))
    server_socket.listen(1)
    print("Nasłuchiwanie danych od Arduino...")

    while True:
        client_socket, client_address = server_socket.accept()

        data = client_socket.recv(1024).decode('utf-8')
        if data:
            try:
                temperature, humidity, voc, co2, groundValue, lightValue, LEDValue = map(float, data.split(','))

                insert_sensor_data(1, temperature)
                insert_sensor_data(2, humidity)
                insert_sensor_data(3, float(groundValue))
                insert_sensor_data(4, float(lightValue))
                insert_sensor_data(5, float(LEDValue))
                insert_sensor_data(6, float(voc))
                insert_sensor_data(7, float(co2))


            except ValueError:
                print("Błąd: Nieprawidłowy format danych od Arduino")

        client_socket.close()

def insert_sensor_data(sensor_id, value):
    try:
        mydb = mysql.connector.connect(**db_params)
        mycursor = mydb.cursor()

        if sensor_id == 1:
            table_name = "sensorreadings_temperatura"
        elif sensor_id == 2:
            table_name = "sensorreadings_wilgotnoscpowietrza"
        elif sensor_id == 3:
            table_name = "sensorreadings_wilgotnoscgleby"
        elif sensor_id == 4:
            table_name = "sensorreadings_natezenieswiatla"
        elif sensor_id == 5:
            table_name = "sensorreadings_jasnoscLED"
        elif sensor_id == 6:
            table_name = "sensorreadings_voc"
        elif sensor_id == 7:
            table_name = "sensorreadings_co2"

        else:
            print(f"Nieprawidłowy identyfikator sensora: {sensor_id}")
            return

        query = f"INSERT INTO {table_name} (Timestamp, SensorID, Value) VALUES (%s, %s, %s)"
        timestamp = datetime.now()
        mycursor.execute(query, (timestamp, sensor_id, value))
        mydb.commit()

    except mysql.connector.Error as err:
        print(f'Błąd: {err}')

    finally:
        if mydb.is_connected():
            mycursor.close()
            mydb.close()




def main():
    data_thread = threading.Thread(target=receive_sensor_data_thread, daemon=True)
    data_thread.start()

    while True:
        print("\nDostępne opcje:")
        print("1. Kontrola parametrów")
        print("2. Dodanie nowej rośliny do stanowiska")
        print("3. Aktualizacja warunków środowiskowych")
        print("4. Usunięcie rośliny")
        print("0. Wyjście")

        choice = input("Wybierz opcję (0-4): ")

        if choice == "0":
            break
        elif choice == "1":
            while True:
                print("\nWybierz które parametry do kontroli:")
                print("1. Temperatura")
                print("2. Wilgotność powietrza")
                print("3. Wilgotność gleby")
                print("4. Natężenie światła")
                print("5. Jasność LED")
                print("6. Poziom VOC")
                print("7. Poziom CO2")
                print("8. Stan wentylatora")
                print("9. Stan grzałki")
                print("10. Stan atomizera")
                print("0. Wyjście")

                choices = input("Wybierz numery tabel oddzielone spacją (0 aby wyjść): ").split()

                if "0" in choices:
                    break

                time_period_hours = int(input("Podaj liczbę godzin, dla których chcesz wyświetlić dane: "))


                table_names = [
                    "SensorReadings_Temperatura",
                    "SensorReadings_WilgotnoscPowietrza",
                    "SensorReadings_WilgotnoscGleby",
                    "SensorReadings_NatezenieSwiatla",
                    "SensorReadings_JasnoscLED",
                    "SensorReadings_VOC",
                    "SensorReadings_CO2",
                    "SensorReadings_StanWentylatora",
                    "SensorReadings_StanGrzalki",
                    "SensorReadings_StanAtomizera",
                ]
                global selected_tables
                selected_tables = []
                selected_tables = [table_names[int(choice) - 1] for choice in choices if
                                   choice.isdigit() and 1 <= int(choice) <= len(table_names)]



                if selected_tables:
                    plot_sensor_data(selected_tables, time_period_hours)
                    ani = FuncAnimation(plt.gcf(), update_plot, interval=1000, cache_frame_data=False)

                    plt.show()
                else:
                    print("Nieprawidłowy wybór. Wybierz numery tabel od 1 do", len(table_names), "lub 0 aby wyjść.")

        elif choice == "2":
            print("\nDostępne rośliny:")
            print("1. Sansevieria")
            print("2. Philodendron")
            print("3. Alocasia")
            print("4. Calathea")
            plant_id_input = input('Podaj ID rośliny, której dane chcesz zaimportować: ')

            try:
                plant_id = int(plant_id_input)
                import_plant_data(plant_id)
            except ValueError:
                print('Podano nieprawidłowe ID rośliny. Wprowadź liczbę całkowitą.')

        elif choice == "3":
            calculate_and_insert_average()


        elif choice == "4":
            plant_id_input = input("Podaj ID rośliny do usunięcia: ")

            num_plants_to_delete_input = input("Podaj ilość roślin do usunięcia: ")

            try:

                plant_id_to_delete = int(plant_id_input)

                num_plants_to_delete = int(num_plants_to_delete_input)

                delete_plant(plant_id_to_delete, num_plants_to_delete)

            except ValueError:

                print("Podano nieprawidłowe ID rośliny lub ilość roślin. Wprowadź liczby całkowite.")

        else:
            print("Nieprawidłowy wybór. Wybierz opcję od 0 do 4.")


if __name__ == "__main__":
    main()
