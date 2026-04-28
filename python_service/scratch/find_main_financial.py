import akshare as ak

def find_main_financial():
    funcs = [f for f in dir(ak) if 'main' in f and 'financial' in f]
    print("Potential functions:")
    for f in funcs:
        print(f" - {f}")

if __name__ == "__main__":
    find_main_financial()
