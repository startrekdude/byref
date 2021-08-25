from byref import byref
from dataclasses import dataclass, field

@dataclass
class Course:
	name : str
	code : str

@dataclass
class Student:
	name    : str
	num     : int
	courses : list = field(default_factory=list)

@byref("s")
def capitalize(s, /):
	s = s.upper()

me = Student("Sam (answers to 'Oh god why')", 1001)
me.courses.append(Course("Fundamentals of Web Applications", "COMP2406"))

def main():
	print(me)
	capitalize(me.courses[0].name)
	capitalize(me.name)
	print(me)
	
	favorite_color = input("What's your favorite color? ")
	capitalize(favorite_color)
	print(f"Your favorite color is: {favorite_color}")

if __name__ == "__main__":
	main()