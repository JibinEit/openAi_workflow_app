class Something {
   Something(this.name, this.value);
  final String name;
  final int value;
  @override
  String toString() => "Something(name: $name, value: $value)";
}