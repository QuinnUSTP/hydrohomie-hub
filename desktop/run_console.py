import time

from desktop.supervisor import Supervisor


def main():
    supervisor = Supervisor()
    supervisor.start_all()
    print("HydroHomie services started. Press Ctrl+C to stop.", flush=True)
    last = None
    try:
        while True:
            status = supervisor.status()
            if status != last:
                print(time.strftime("%H:%M:%S"), status, flush=True)
                last = status
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.stop_all()
        print("Stopped.")


if __name__ == "__main__":
    main()