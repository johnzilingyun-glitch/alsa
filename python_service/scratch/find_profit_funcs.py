import akshare as ak

def find_net_profit_funcs():
    funcs = [f for f in dir(ak) if 'profit' in f or 'income' in f or 'revenue' in f]
    print("Potential functions:")
    for f in funcs:
        print(f" - {f}")

if __name__ == "__main__":
    find_net_profit_funcs()
