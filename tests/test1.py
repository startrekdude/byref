from byref import byref

@byref("a")
def add(a, b, /):
	a += b

a = 50
add(a, 10)
print(a)

@byref("x")
def add_all(x, ys, /):
	for y in ys:
		x += y

test_array = [10, 20, 30, 40, 50]
add_all(test_array[0], test_array[1:])
print(test_array[0])