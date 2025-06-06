// dirty_class.dart

import 'dart:async';      // bad: unused import
import 'dart:io';         // bad: using dart:io in Flutter context (blocks UI, not allowed on web)
import 'dart:convert';    // bad: unused import
import 'package:flutter/widgets.dart'; // bad: mixing UI imports in a logic‐only class

// bad: class name not in PascalCase, not following Dart style
class dirtyclass {
  // bad: public mutable fields with poor naming
  var x = 0;                         
  String? y;                         
  List items = [];                   // bad: raw List type, no generics
  static Map cache = {};             // bad: raw Map type, global mutable state

  // bad: side effects (I/O) in constructor, blocking operations
  dirtyclass() {
    print("dirtyclass constructed");   // bad: print statements for logging
    y = "hello";                       
    items.add(null);                   // bad: adding null to a non-nullable collection
    sleep(Duration(seconds: 1));       // bad: synchronous sleep blocks the event loop
    _loadConfig();                     // bad: I/O in constructor
  }

  // bad: private helper doing blocking I/O
  void _loadConfig() {
    try {
      // bad: reading file synchronously
      final data = File('config.json').readAsStringSync(); 
      var decoded = jsonDecode(data);       // bad: unused decoded data
      cache['config'] = decoded;            // bad: storing unvalidated data in global
      print("Config loaded: $decoded");     // bad: logging raw data
    } catch (e) {
      print("Error loading config: $e");    // bad: broad catch, no rethrow
    }
  }

  // bad: overly large method, multiple responsibilities, deeply nested
  Future<void> performTask(int number, String text, bool flag) async {
    // bad: no input validation
    if (flag) {
      for (int i = 0; i < number; i++) {
        // bad: doing computation on main thread, no isolates
        x += i * 2;                           
        items.add(i);                         // bad: mixing numbers in a List<Object>
      }
    } else {
      int result = 0;
      for (int i = number; i > 0; i--) {
        // bad: nested loops, potential O(n^2) runtime
        for (int j = 0; j < i; j++) {
          result += j;
        }
      }
      x = result;                             // bad: overwriting x with a derived value
    }

    // bad: poor naming, unclear purpose
    var tmp = await _longNetworkCall();        // bad: network call without timeout handling
    print("Network returned: $tmp");           // bad: logging raw network response

    if (tmp.contains('error')) {
      // bad: catching string search as error detection
      throw Exception("Network error: $tmp");  // bad: throwing generic Exception
    }

    // bad: UI code inside a logic method
    
    // bad: returning void despite performing work
  }

  // bad: network call simulating without proper exception handling
  Future<String> _longNetworkCall() async {
    await Future.delayed(Duration(seconds: 3));  // bad: fake delay in production code
    return "OK";                                 // bad: returning magic string
  }

  // bad: static method that mixes concerns
  static void staticHelper() {
    print("Static helper called");               // bad: print for production logging
    // bad: modifying global state arbitrarily
    cache['lastCalled'] = DateTime.now();        
  }

  // bad: public method exposing internal state
  List getItems() {
    return items;                                // bad: returning internal list reference
  }

  // bad: setter with no validation
  void setItemAt(int index, Object? value) {
    // bad: no index bounds check
    items[index] = value;                        
  }

  // bad: mixing async and sync without purpose
  Future<bool> saveData() async {
    try {
      // bad: writing file synchronously in async method
      File('output.txt').writeAsStringSync(items.toString());
      return true; 
    } catch (e) {
      print("Save failed: $e");                  // bad: broad catch
      return false; 
    }
  }
}

void main() {
  // bad: creating widget in a non-Flutter context
  dirtyclass dc = dirtyclass();                 
                             

  // bad: direct use of print in main
  print("Final items: ${dc.getItems()}");        
}