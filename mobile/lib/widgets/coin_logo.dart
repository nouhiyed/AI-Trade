import 'package:flutter/material.dart';

/// Prefers Binance's hosted asset logo, then uses a ticker-based fallback.
class CoinLogo extends StatefulWidget {
  final String symbol;
  final double size;
  const CoinLogo({super.key, required this.symbol, this.size = 28});
  @override
  State<CoinLogo> createState() => _CoinLogoState();
}

class _CoinLogoState extends State<CoinLogo> {
  static final Map<String, Future<String?>> _cache = {};
  String get _ticker {
    var value = widget.symbol.toLowerCase().replaceAll('usdt', '').replaceAll('usdc', '');
    if (value.startsWith('1000')) value = value.substring(4);
    value = value.replaceAll(RegExp(r'[^a-z0-9]'), '');
    const aliases = {'xbt': 'btc', 'bcc': 'bch', 'bcha': 'bch'};
    return aliases[value] ?? value;
  }

  Future<String?> _resolve() async {
    if (_ticker.isEmpty) return null;
    return 'https://bin.bnbstatic.com/static/assets/logos/$_ticker.png';
  }

  @override
  Widget build(BuildContext context) {
    final fallback = Icon(Icons.currency_bitcoin, size: widget.size * .68,
      color: Theme.of(context).colorScheme.primary);
    return Container(
      width: widget.size, height: widget.size,
      decoration: BoxDecoration(shape: BoxShape.circle,
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        border: Border.all(color: Theme.of(context).dividerColor.withOpacity(.25))),
      clipBehavior: Clip.antiAlias,
      child: FutureBuilder<String?>(
        future: _resolve(),
        builder: (context, snapshot) {
          if (snapshot.data == null) return fallback;
          return Image.network(
            snapshot.data!,
            width: widget.size,
            height: widget.size,
            fit: BoxFit.contain,
            errorBuilder: (_, __, ___) => Image.network(
              'https://assets.coincap.io/assets/icons/$_ticker@2x.png',
              width: widget.size,
              height: widget.size,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => fallback,
            ),
          );
        },
      ),
    );
  }
}
