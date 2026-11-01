import sys

from rates_forecasting.evaluation.policy import run_policy

if __name__ == "__main__":
    print(run_policy(*sys.argv[1:2]))
