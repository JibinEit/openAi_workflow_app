class Calculator {
  /// Adds two numbers and returns the result.
  double add(double a, double b) => a + b;

  /// Subtracts [b] from [a] and returns the result.
  double subtract(double a, double b) => a - b;

  /// Multiplies two numbers and returns the result.
  double multiply(double a, double b) => a * b;

  /// Divides [a] by [b] and returns the result.
  /// Throws [ArgumentError] if [b] is zero.
  double divide(double a, double b) {
    if (b == 0) {
      throw ArgumentError('Cannot divide by zero');
    }
    return a / b;
  }
}