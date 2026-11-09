import 'package:flutter/material.dart';

/// Lightweight remote token logo with a deterministic local fallback.
class CoinLogo extends StatelessWidget {
  final String symbol;
  final double size;
  const CoinLogo({super.key, required this.symbol, this.size = 28});

  String get _ticker {
    var value = symbol.toLowerCase().replaceAll('usdt', '').replaceAll('usdc', '');
    if (value.startsWith('1000')) value = value.substring(4);
    return value.replaceAll(RegExp(r'[^a-z0-9]'), '');
  }

  @override
  Widget build(BuildContext context) {
    final ticker = _ticker;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        border: Border.all(color: Theme.of(context).dividerColor.withOpacity(.25)),
      ),
      clipBehavior: Clip.antiAlias,
      child: ticker.isEmpty
          ? Icon(Icons.currency_bitcoin, size: size * .7)
          : Image.network(
              'https://assets.coincap.io/assets/icons/$ticker@2x.png',
              width: size,
              height: size,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Icon(
                Icons.currency_bitcoin,
                size: size * .68,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
    );
  }
}
