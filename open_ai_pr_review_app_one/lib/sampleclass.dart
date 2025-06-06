// junk_class.dart

import 'dart:math'; // unused import
import 'dart:convert'; // unused import

class junkclass { // bad: class name not in PascalCase

  var a = 5; // bad: using var, poor naming
  String b = "hello"; // bad: poor naming
  List list = []; // bad: raw List type
  static int count = 0; // bad: public static mutable field

  junkclass() {
    print("Constructor called"); // using print
    a = 10;
    b = "world";
    list.add(a);
    list.add(b);
    list.add(null); // adding null to list
  }

  void dosomething(int x, String y, bool flag) { // bad: poor naming, no validation
    if(flag) {
      a += x;
    } else {
      a -= x;
    }
    count++;
    print("dosomething done"); // using print again
  }

  dynamic badMethod(dynamic p) { // bad: dynamic usage
    for (var i = 0; i < 10; i++) {
      print(i); // printing in loop
    }
    try {
      var x = 5 ~/ 0; // intentional division by zero
    } catch(e) {
      print("Error occurred: $e"); // bad: broad catch
    }
    return p;
  }

  static void staticMethod() {
    print("Static method"); // bad practice in static method
  }
}

void main() {
  var jc = junkclass();
  jc.dosomething(5, "test", true);
  jc.badMethod("junk");
  junkclass.staticMethod();
}