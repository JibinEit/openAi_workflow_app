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
  Widget build(final BuildContext context) => Center(
        child: Container(
          width: width,
          height: height,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(30),
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: Colors.black.withAlpha((0.2 * 255).toInt()),
                blurRadius: 30,
                offset: const Offset(0, 10),
              ),
              BoxShadow(
                color: Colors.white.withAlpha((0.05 * 255).toInt()),
                blurRadius: 10,
                spreadRadius: 1,
                offset: const Offset(-5, -5),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(30),
            child: Stack(
              children: <Widget>[
                // The blur effect
                BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
                  child: Container(
                    color: Colors.white.withAlpha((0.1 * 255).toInt()),
                  ),
                ),
                // Glass gradient overlay (simulates light reflection)
                Container(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: <Color>[
                        Colors.white.withAlpha((0.4 * 255).toInt()),
                        Colors.white.withAlpha((0.05 * 255).toInt()),
                      ],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(30),
                    border: Border.all(
                      color: Colors.white.withAlpha((0.3 * 255).toInt()),
                      width: 1.5,
                    ),
                  ),
                ),
                // Light reflection shine
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: Container(
                    height: height * 0.4,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: <Color>[
                          Colors.white.withAlpha((0.35 * 255).toInt()),
                          Colors.transparent,
                        ],
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                      ),
                    ),
                  ),
                ),
                // Child content
                Center(child: child),
              ],
            ),
          ),
        ),
      );
}