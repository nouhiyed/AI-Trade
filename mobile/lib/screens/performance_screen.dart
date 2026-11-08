import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_service.dart';

const _green = Color(0xFF21D6A1);
const _red = Color(0xFFFF647C);
const _blue = Color(0xFF39A8FF);
const _violet = Color(0xFF9B72FF);

/// Autopilot control, performance metrics, learning status and trade journal.
class PerformanceScreen extends StatefulWidget {
  final bool english;
  final Color bg, panel, text, muted;

  const PerformanceScreen({
    super.key,
    required this.english,
    required this.bg,
    required this.panel,
    required this.text,
    required this.muted,
  });

  @override
  State<PerformanceScreen> createState() => _PerformanceScreenState();
}

class _PerformanceScreenState extends State<PerformanceScreen> {
  Map<String, dynamic> _perf = {};
  Map<String, dynamic> _learning = {};
  Map<String, dynamic> _auto = {};
  List<Map<String, dynamic>> _trades = [];
  bool _busy = false;
  String? _error;
  Timer? _timer;

  String t(String ar, String en) => widget.english ? en : ar;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Map<String, dynamic> _map(dynamic v) =>
      v is Map ? Map<String, dynamic>.from(v) : <String, dynamic>{};

  Future<void> _load() async {
    if (_busy) return;
    _busy = true;
    try {
      final perf = await ApiService.performance();
      final learning = await ApiService.learning();
      final auto = await ApiService.autopilot();
      final journal = await ApiService.journal(limit: 30);
      final rows = journal['trades'];
      if (!mounted) return;
      setState(() {
        _perf = perf;
        _learning = learning;
        _auto = auto;
        _trades = rows is List
            ? rows.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
            : <Map<String, dynamic>>[];
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      _busy = false;
    }
  }

  Future<void> _setAuto(Map<String, dynamic> changes) async {
    try {
      final result = await ApiService.autopilotUpdate(changes);
      if (mounted) setState(() => _auto = result);
    } catch (e) {
      _toast('$e');
    }
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Widget _card(Widget child) => Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: widget.panel,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: widget.muted.withOpacity(.18)),
        ),
        child: child,
      );

  Widget _title(String s) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text(
          s,
          style: TextStyle(
            color: widget.text,
            fontWeight: FontWeight.w900,
            fontSize: 13,
          ),
        ),
      );

  Widget _tile(String label, String value, [Color? color]) => SizedBox(
        width: 104,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(color: widget.muted, fontSize: 10)),
            const SizedBox(height: 3),
            Text(
              value,
              style: TextStyle(
                color: color ?? widget.text,
                fontWeight: FontWeight.w900,
                fontSize: 15,
              ),
            ),
          ],
        ),
      );

  String _n(dynamic v, [int digits = 2]) {
    final d = double.tryParse('$v');
    return d == null ? '—' : d.toStringAsFixed(digits);
  }

  Widget _autopilotCard() {
    final cfg = _map(_auto['config']);
    final enabled = cfg['enabled'] == true;
    final minConf = (double.tryParse('${cfg['min_confidence']}') ?? 60.0).clamp(25.0, 100.0).toDouble();
    final maxConc = (double.tryParse('${cfg['max_concurrent']}') ?? 3.0).clamp(1.0, 5.0).toDouble();
    final risk = (double.tryParse('${cfg['risk_pct']}') ?? 0.5).clamp(0.1, 1.0).toDouble();
    final last = _map(_auto['last_result']);
    final opened = last['opened'] is List ? (last['opened'] as List).length : 0;
    final rejections = _map(last['rejections']);
    final skipped = last['skipped'] is List
        ? (last['skipped'] as List).whereType<Map>().take(4).toList()
        : <Map>[];

    Widget slider(String label, double value, double min, double max,
        int? divisions, String key, {bool asInt = false}) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$label: ${asInt ? value.round() : value.toStringAsFixed(2)}',
              style: TextStyle(color: widget.muted, fontSize: 11)),
          Slider(
            value: value,
            min: min,
            max: max,
            divisions: divisions,
            onChanged: (v) => setState(() {
              cfg[key] = asInt ? v.round() : v;
              _auto['config'] = cfg;
            }),
            onChangeEnd: (v) => _setAuto({key: asInt ? v.round() : v}),
          ),
        ],
      );
    }

    return _card(Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: _title(t('التداول الآلي (DEMO)', 'Autopilot (DEMO)'))),
            Switch(
              value: enabled,
              activeColor: _green,
              onChanged: (v) => _setAuto({'enabled': v}),
            ),
          ],
        ),
        Text(
          enabled
              ? t('يعمل: يفحص السوق ويفتح صفقات تجريبية تلقائياً.',
                  'Running: scans the market and opens demo trades automatically.')
              : t('متوقف. شغّله ليبدأ الوكيل بالتداول التجريبي.',
                  'Off. Turn it on to let the agent trade in demo.'),
          style: TextStyle(color: widget.muted, fontSize: 11),
        ),
        Wrap(
          spacing: 8,
          children: [
            for (final m in const ['futures', 'spot', 'alpha'])
              FilterChip(
                label: Text(m.toUpperCase(), style: const TextStyle(fontSize: 11)),
                selected: cfg['trade_$m'] != false,
                visualDensity: VisualDensity.compact,
                onSelected: (v) {
                  setState(() {
                    cfg['trade_$m'] = v;
                    _auto['config'] = cfg;
                  });
                  _setAuto({'trade_$m': v});
                },
              ),
          ],
        ),
        slider(t('أدنى ثقة', 'Min confidence'), minConf, 25, 100, 15, 'min_confidence'),
        slider(t('أقصى صفقات متزامنة', 'Max concurrent trades'), maxConc, 1, 5, 4,
            'max_concurrent', asInt: true),
        slider(t('المخاطرة لكل صفقة %', 'Risk per trade %'), risk, 0.1, 1.0, 9, 'risk_pct'),
        Row(
          children: [
            OutlinedButton.icon(
              onPressed: () async {
                try {
                  final r = await ApiService.autopilotRun();
                  final n = r['opened'] is List ? (r['opened'] as List).length : 0;
                  _toast(t('تم الفحص: فُتحت $n صفقة', 'Scan done: $n trade(s) opened'));
                  _load();
                } catch (e) {
                  _toast('$e');
                }
              },
              icon: const Icon(Icons.radar, size: 16),
              label: Text(t('افحص الآن', 'Scan now')),
            ),
            const SizedBox(width: 10),
            Text(
              '${t('آخر دورة', 'Last cycle')}: $opened ${t('صفقة', 'opened')}',
              style: TextStyle(color: widget.muted, fontSize: 10),
            ),
          ],
        ),
        if (last.isNotEmpty) ...[
          const SizedBox(height: 9),
          Text(
            '${t('فُحص', 'Scanned')} ${last['scanned'] ?? 0} · '
            '${t('فرص قابلة للتنفيذ', 'Actionable')} ${last['actionable'] ?? 0}',
            style: TextStyle(color: widget.muted, fontSize: 10),
          ),
          for (final domainEntry in rejections.entries)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                '${domainEntry.key.toString().toUpperCase()}: '
                '${_map(domainEntry.value).entries.map((e) => '${e.key} (${e.value})').join(' · ')}',
                style: TextStyle(color: widget.muted, fontSize: 10),
              ),
            ),
          for (final item in skipped)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text(
                '${item['domain'] ?? ''} ${item['symbol'] ?? ''}: ${item['reason'] ?? ''}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: _red, fontSize: 10),
              ),
            ),
        ],
      ],
    ));
  }

  Widget _metricsCard() {
    final o = _map(_perf['overall']);
    final net = double.tryParse('${o['net_pnl']}') ?? 0;
    return _card(Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _title(t('الأداء', 'Performance')),
        Wrap(
          runSpacing: 12,
          spacing: 6,
          children: [
            _tile(t('الصفقات', 'Trades'), '${o['trades'] ?? 0}'),
            _tile(t('نسبة الفوز', 'Win rate'), '${_n(o['win_rate'], 1)}%'),
            _tile(t('صافي الربح', 'Net PnL'), _n(o['net_pnl']),
                net >= 0 ? _green : _red),
            _tile(t('معامل الربح', 'Profit factor'), _n(o['profit_factor'])),
            _tile(t('التوقع (R)', 'Expectancy R'), _n(o['expectancy_r'])),
            _tile(t('أقصى تراجع', 'Max drawdown'), _n(o['max_drawdown']), _red),
          ],
        ),
        const SizedBox(height: 12),
        SizedBox(
          height: 90,
          width: double.infinity,
          child: CustomPaint(
            painter: _CurvePainter(
              (_perf['equity_curve'] is List)
                  ? (_perf['equity_curve'] as List)
                      .map((e) => (e as num).toDouble())
                      .toList()
                  : <double>[],
              widget.muted,
            ),
          ),
        ),
      ],
    ));
  }

  Widget _learningCard() {
    final setups = _learning['setups'] is List
        ? (_learning['setups'] as List).whereType<Map>().toList()
        : <Map>[];
    final suggestions = _learning['suggestions'] is List
        ? (_learning['suggestions'] as List).map((e) => '$e').toList()
        : <String>[];
    final minSamples = _learning['min_samples'] ?? 30;
    return _card(Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _title(t('التعلّم الذاتي', 'Learning')),
        Text(
          t('لا تغيير قبل $minSamples صفقة مغلقة لكل نمط. النمط الخاسر يُوقَف تلقائياً.',
              'No change before $minSamples closed trades per setup. Losing setups are paused automatically.'),
          style: TextStyle(color: widget.muted, fontSize: 11),
        ),
        const SizedBox(height: 8),
        for (final tip in suggestions)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text('• $tip', style: TextStyle(color: widget.text, fontSize: 11)),
          ),
        for (final s in setups)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${s['setup']}',
                          style: TextStyle(
                              color: widget.text,
                              fontWeight: FontWeight.bold,
                              fontSize: 12)),
                      Text(
                        '${s['trades']} ${t('صفقة', 'trades')} · '
                        '${t('فوز', 'win')} ${_n(s['win_rate'], 0)}% · '
                        'R ${_n(s['expectancy_r'])}'
                        '${s['mature'] == true ? '' : ' · ${t('غير ناضج', 'immature')}'}',
                        style: TextStyle(color: widget.muted, fontSize: 10),
                      ),
                    ],
                  ),
                ),
                if (s['disabled'] == true)
                  TextButton(
                    onPressed: () async {
                      try {
                        await ApiService.enableSetup('${s['setup']}');
                        _load();
                      } catch (e) {
                        _toast('$e');
                      }
                    },
                    child: Text(t('إعادة تفعيل', 'Re-enable')),
                  )
                else
                  Icon(Icons.check_circle,
                      size: 16, color: s['mature'] == true ? _green : _blue),
              ],
            ),
          ),
      ],
    ));
  }

  Widget _tradesCard() => _card(Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _title(t('سجل الصفقات', 'Trade journal')),
          if (_trades.isEmpty)
            Text(t('لا توجد صفقات بعد.', 'No trades yet.'),
                style: TextStyle(color: widget.muted, fontSize: 11)),
          for (final tr in _trades)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: ('${tr['direction']}' == 'LONG' ? _green : _red)
                          .withOpacity(.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text('${tr['direction']}',
                        style: TextStyle(
                            color: '${tr['direction']}' == 'LONG' ? _green : _red,
                            fontSize: 10,
                            fontWeight: FontWeight.bold)),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${tr['symbol']}',
                            style: TextStyle(
                                color: widget.text,
                                fontWeight: FontWeight.bold,
                                fontSize: 12)),
                        Text(
                          '${tr['status'] == 'OPEN' ? t('مفتوحة', 'OPEN') : (tr['close_reason'] ?? '')}'
                          ' · ${t('ثقة', 'conf')} ${_n(tr['confidence'], 0)}',
                          style: TextStyle(color: widget.muted, fontSize: 10),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    tr['net_pnl'] == null ? '—' : _n(tr['net_pnl'], 3),
                    style: TextStyle(
                      color: (double.tryParse('${tr['net_pnl']}') ?? 0) >= 0
                          ? _green
                          : _red,
                      fontWeight: FontWeight.w900,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ));

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: widget.english ? TextDirection.ltr : TextDirection.rtl,
      child: Scaffold(
        backgroundColor: widget.bg,
        appBar: AppBar(
          backgroundColor: widget.panel,
          foregroundColor: widget.text,
          title: Text(t('الأداء والتداول الآلي', 'Performance & Autopilot')),
          actions: [
            IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
          ],
        ),
        body: ListView(
          padding: const EdgeInsets.all(14),
          children: [
            if (_error != null)
              _card(Text(
                t('الخادم غير متصل. شغّله في Termux ثم حدّث.',
                    'Server unreachable. Start it in Termux and refresh.'),
                style: const TextStyle(color: _red, fontSize: 12),
              )),
            _autopilotCard(),
            _metricsCard(),
            _learningCard(),
            _tradesCard(),
            Text(
              t('نتائج الديمو أفضل غالباً من الحقيقة (انزلاق وتأخر تنفيذ). لا تنتقل للحقيقي قبل مئة صفقة على الأقل.',
                  'Demo results are usually better than real (slippage, latency). Do not go live before at least 100 trades.'),
              style: TextStyle(color: widget.muted, fontSize: 10),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }
}

class _CurvePainter extends CustomPainter {
  final List<double> values;
  final Color muted;
  _CurvePainter(this.values, this.muted);

  @override
  void paint(Canvas canvas, Size size) {
    final axis = Paint()
      ..color = muted.withOpacity(.3)
      ..strokeWidth = 1;
    if (values.length < 2) {
      canvas.drawLine(Offset(0, size.height / 2),
          Offset(size.width, size.height / 2), axis);
      return;
    }
    var lo = values.first, hi = values.first;
    for (final v in values) {
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (lo > 0) lo = 0;
    if (hi < 0) hi = 0;
    final span = (hi - lo) == 0 ? 1.0 : (hi - lo);
    double y(double v) => size.height - (v - lo) / span * size.height;
    canvas.drawLine(Offset(0, y(0)), Offset(size.width, y(0)), axis);
    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final x = i / (values.length - 1) * size.width;
      if (i == 0) {
        path.moveTo(x, y(values[i]));
      } else {
        path.lineTo(x, y(values[i]));
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..color = values.last >= 0 ? _green : _red,
    );
  }

  @override
  bool shouldRepaint(covariant _CurvePainter old) =>
      old.values != values || old.muted != muted;
}
