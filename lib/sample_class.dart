class Something {
   Something(this.name, this.value);
  final String name;
  final int value;
  final String? description;
  @override
  String toString() => "Something(name: $name, value: $value)";
}