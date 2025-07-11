import "package:flutter/material.dart";

import "liquid_glass.dart" show LiquidGlassWidget;

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(final BuildContext context) => MaterialApp(
        title: "Flutter Demo",
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
          useMaterial3: true,
        ),
        home: const MyHomePage(title: "Flutter Demo Home Page"),
      );
}

class MyHomePage extends StatefulWidget {
  const MyHomePage({required this.title, super.key});

  final String title;

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  int _clickCount = 0;

  void _incrementClickCount() {
    setState(() {
      _clickCount += 1;
    });
  }

  @override
  Widget build(final BuildContext context) => Scaffold(
    backgroundColor: Colors.green,
        appBar: AppBar(
          backgroundColor: () {
            final Color inversePrimaryColor =
                Theme.of(context).colorScheme.inversePrimary;
            return inversePrimaryColor;
          }(),
          title: Text(widget.title),
        ),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              Text(
                _clickCount.toString(),
              ),
              Text(
                "$_clickCount",
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              Row(
                children: <Widget>[
                  const Text("Hello World in Binary: "),
                  Text(
                    textToBinary("Hello World"),
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
              ),
              const LiquidGlassWidget(
                child: Center(
                  child: Text(
                    "Liquid Glass",
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        floatingActionButton: FloatingActionButton(
          onPressed:
              textToBinary("Hello World").isEmpty ? null : _incrementClickCount,
          child: const Icon(Icons.add, semanticLabel: "Add One"),
        ),
      );
}

String textToBinary(final String text) => text.runes
    .map((final int rune) => rune.toRadixString(2).padLeft(8, "0"))
    .join(" ");
