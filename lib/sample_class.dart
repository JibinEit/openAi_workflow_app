class Something {
  Something(this.name, this.value, {this.description} );
  final String name;
  final int value;
  final String? description;
  final String _privateField = "This is private";
  String get privateField => _privateField ;
  String get fullDescription => "$name: $value${description != null ? ' - $description' : ''}";
 
} 