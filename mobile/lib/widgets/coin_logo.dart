import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

/// Resolves symbols against Binance's own asset registry (asset -> official pic URL).
class CoinLogo extends StatefulWidget {
  final String symbol;
  final double size;
  const CoinLogo({super.key, required this.symbol, this.size = 28});

  @override
  State<CoinLogo> createState() => _CoinLogoState();
}

class _CoinLogoState extends State<CoinLogo> {
  static Future<Map<String, String>>? _binanceAssets;

  String get _ticker {
    var value = widget.symbol.toUpperCase()
        .replaceAll('USDT', '')
        .replaceAll('USDC', '')
        .replaceAll('BUSD', '')
        .replaceAll('FDUSD', '');
    if (value.startsWith('1000')) value = value.substring(4);
    value = value.replaceAll(RegExp(r'[^A-Z0-9]'), '');
    const aliases = {'XBT': 'BTC', 'BCC': 'BCH', 'BCHA': 'BCH'};
    return aliases[value] ?? value;
  }

  static Future<Map<String, String>> _loadBinanceAssets() {
    return _binanceAssets ??= () async {
      final result = <String, String>{};
      try {
        final response = await http.get(
          Uri.https(
            'www.binance.com',
            '/bapi/asset/v1/public/asset-service/product/currency',
          ),
          headers: const {'accept': 'application/json'},
        ).timeout(const Duration(seconds: 12));
        if (response.statusCode == 200) {
          final decoded = jsonDecode(response.body);
          final raw = decoded is Map ? decoded['data'] : null;
          if (raw is List) {
            for (final item in raw) {
              if (item is Map) {
                final asset = '${item['asset'] ?? ''}'.toUpperCase();
                final pic = '${item['pic'] ?? ''}';
                if (asset.isNotEmpty && pic.startsWith('https://')) {
                  result[asset] = pic;
                }
              }
            }
          }
        }
      } catch (_) {}
      return result;
    }();
  }

  Future<String?> _resolve() async {
    final ticker = _ticker;
    if (ticker.isEmpty) return null;
    final assets = await _loadBinanceAssets();
    return assets[ticker] ??
        'https://cdn.jsdelivr.net/gh/prasangapokharel/crypto-icons@v1.0.0/binance/$ticker.png';
  }

  @override
  Widget build(BuildContext context) {
    final fallback = Icon(
      Icons.currency_bitcoin,
      size: widget.size * .68,
      color: Theme.of(context).colorScheme.primary,
    );
    return Container(
      width: widget.size,
      height: widget.size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        border: Border.all(
          color: Theme.of(context).dividerColor.withOpacity(.25),
        ),
      ),
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
              'https://assets.coincap.io/assets/icons/${_ticker.toLowerCase()}@2x.png',
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
