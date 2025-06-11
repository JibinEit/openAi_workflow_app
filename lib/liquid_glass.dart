

import "dart:ui";

import "package:flutter/material.dart";

class LiquidGlassWidget extends StatelessWidget {

  const LiquidGlassWidget({
    super.key,
    this.width = 300,
    this.height = 200,
    this.child,
  });
  final double width;
  final double height;
  final Widget? child;

  @override
  Widget build(final BuildContext context) =>
     ClipRRect(
      borderRadius: BorderRadius.circular(25),
      child: Stack(
        children: <Widget>[
          // Background blur
          BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: Container(
              width: width,
              height: height,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: <Color>[
                    Colors.white.withAlpha(51),
                    Colors.white.withAlpha(13),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(25),
                border: Border.all(
                  color: Colors.white.withAlpha((0.3 * 255).toInt()),
                  width: 1.5,
                ),
              ),
              child: child,
            ),
          ),
        ],
      ),
    );

}