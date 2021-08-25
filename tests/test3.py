from byref import byref

@byref("x")
def add(x, /, *xs):
	for y in xs:
		x += y

def main():
	nums = []
	while True:
		s = input("Enter a number? ")
		if not s: break
		if not s.isdigit(): continue
		nums.append(int(s))
	
	x, *xs = nums
	add(x, *xs)
	
	print(f"The sum of these numbers is {x}.")
	print("Goodbye.")

if __name__ == "__main__":
	main()