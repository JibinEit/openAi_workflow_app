class SampleClass {
  SampleClass(this.a, this.b, this.age);

  final String a;
  final String b;
  final int age;

  @override
  String toString() => "SampleClass(a: $a, b: $b, age: $age)";

  Future<void> domething() async {
    await delayed;
    print("Doing something with $a and $b at age $age");
  }
}
