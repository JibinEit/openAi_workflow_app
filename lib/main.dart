import 'package:flutter/material.dart';
import 'package:open_ai_pr_review_app_one/sampleclass.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      home: const MyHomePage(title: 'Flutter Demo Home Page'),
    );
  }
}

class MyHomePage extends StatefulWidget {
  const MyHomePage({super.key, required this.title});

  final String title;

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  int _counter = 0;

  void _incrementCounter() {
    setState(() {
      _counter++;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        title: Text(widget.title),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            const Text(
              'You have pushed the button this many times:',
            ),
            Text(
              '$_counter',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          _incrementCounter();
        
          SampleClass sample = SampleClass();   
          sample.sampleMethod(); // Call the method from SampleClass
          print('SampleClass method called');
          // You can also use the sample object to access other properties or methods 

          // if needed. 
          // For example, you can access sample.someProperty if it exists.
          // This is just an example of how to use the SampleClass in your app.
          // Make sure to import the SampleClass file at the top of this file.


              int a;
              int b;

              a = 5;
              b = 10; 
              int sum = a + b; // This will calculate the sum of a and b
              print('The sum of $a and $b is $sum'); // This will print the sum to the console
              // You can use this sum variable in your app as needed.
          
        },
        tooltip: 'Increment',
        child: const Icon(Icons.add),
      ),
    );
  }
}
