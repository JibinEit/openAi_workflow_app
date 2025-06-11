import 'dart:ui';
import 'package:flutter/material.dart';

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
  Widget build(final BuildContext context) {
    return Center(
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(30),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.2),
              blurRadius: 30,
              offset: const Offset(0, 10),
            ),
            BoxShadow(
              color: Colors.white.withOpacity(0.05),
              blurRadius: 10,
              spreadRadius: 1,
              offset: const Offset(-5, -5),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(30),
          child: Stack(
            children: [
              // The blur effect
              BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
                child: Container(
                  color: Colors.white.withOpacity(0.1),
                ),
              ),
              // Glass gradient overlay (simulates light reflection)
              Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      Colors.white.withOpacity(0.4),
                      Colors.white.withOpacity(0.05),
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(30),
                  border: Border.all(
                    color: Colors.white.withOpacity(0.3),
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
                      colors: [
                        Colors.white.withOpacity(0.35),
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
}