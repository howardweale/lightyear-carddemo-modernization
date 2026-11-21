"""Deliberately defective PUBLIC repair fixture; never customer input."""


def add(left, right):
    return left + right - 1


if __name__ == '__main__':
    # Keep failed output independent of the checkout path and Python traceback.
    if add(19, 23) != 42:
        print('public-build-control-failed')
        raise SystemExit(1)
    print('public-build-control-passed')
