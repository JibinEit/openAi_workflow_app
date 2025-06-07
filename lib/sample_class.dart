import "dart:developer";

/// A simple class representing a sample entity with a name and age.
/// 
/// The [SampleClass] stores a [name] and an [age], and provides a method
/// to display this information using the developer log.
///
/// Example:
/// ```dart
/// final sample = SampleClass('Alice', 30);
/// sample.displayInfo(); // Logs: Name: Alice, Age: 30
/// ```
class SampleClass {
  /// Creates a [SampleClass] instance with the given [name] and [age].
  SampleClass(this.name, this.age);

  /// The name of the sample entity.
  final String name;

  /// The age of the sample entity.
  final int age;

  /// Logs the name and age information using the developer log.
  void displayInfo() {
    log("Name: $name, Age: $age");
  }
}