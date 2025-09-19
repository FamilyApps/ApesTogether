#!/usr/bin/env python3
"""
MARKET CLOSE MONITORING SYSTEM
Comprehensive diagnostics for the daily market close pipeline
"""

import os
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

class StepStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress" 
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class StepResult:
    step_name: str
    status: StepStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    records_processed: int = 0
    errors: List[str] = None
    warnings: List[str] = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.details is None:
            self.details = {}

class MarketCloseMonitor:
    def __init__(self):
        self.pipeline_steps = [
            "alpha_vantage_calls",
            "portfolio_snapshots", 
            "leaderboard_calculation",
            "html_prerendering",
            "chart_generation",
            "cache_cleanup"
        ]
        self.results = {}
        self.pipeline_start_time = None
        self.pipeline_end_time = None
        
    def start_pipeline(self):
        """Start monitoring the entire pipeline"""
        self.pipeline_start_time = datetime.now()
        print(f"🚀 MARKET CLOSE PIPELINE STARTED: {self.pipeline_start_time}")
        
        # Initialize all steps
        for step in self.pipeline_steps:
            self.results[step] = StepResult(
                step_name=step,
                status=StepStatus.NOT_STARTED
            )
    
    def start_step(self, step_name: str):
        """Mark a step as started"""
        if step_name not in self.results:
            self.results[step_name] = StepResult(step_name=step_name, status=StepStatus.NOT_STARTED)
        
        self.results[step_name].status = StepStatus.IN_PROGRESS
        self.results[step_name].start_time = datetime.now()
        print(f"▶️  STARTING: {step_name} at {self.results[step_name].start_time}")
    
    def complete_step(self, step_name: str, success: bool = True, 
                     records_processed: int = 0, errors: List[str] = None, 
                     warnings: List[str] = None, details: Dict[str, Any] = None):
        """Mark a step as completed"""
        if step_name not in self.results:
            return
        
        step = self.results[step_name]
        step.end_time = datetime.now()
        step.status = StepStatus.SUCCESS if success else StepStatus.FAILED
        step.records_processed = records_processed
        
        if step.start_time:
            step.duration_seconds = (step.end_time - step.start_time).total_seconds()
        
        if errors:
            step.errors.extend(errors)
        if warnings:
            step.warnings.extend(warnings)
        if details:
            step.details.update(details)
        
        status_icon = "✅" if success else "❌"
        print(f"{status_icon} COMPLETED: {step_name} - {step.duration_seconds:.1f}s - {records_processed} records")
        
        if errors:
            for error in errors:
                print(f"   ❌ ERROR: {error}")
        if warnings:
            for warning in warnings:
                print(f"   ⚠️  WARNING: {warning}")
    
    def end_pipeline(self):
        """End monitoring and generate report"""
        self.pipeline_end_time = datetime.now()
        total_duration = (self.pipeline_end_time - self.pipeline_start_time).total_seconds()
        
        print(f"\n🏁 MARKET CLOSE PIPELINE COMPLETED: {self.pipeline_end_time}")
        print(f"⏱️  Total Duration: {total_duration:.1f} seconds")
        
        return self.generate_report()
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive monitoring report"""
        total_records = sum(step.records_processed for step in self.results.values())
        total_errors = sum(len(step.errors) for step in self.results.values())
        total_warnings = sum(len(step.warnings) for step in self.results.values())
        
        successful_steps = [name for name, step in self.results.items() 
                          if step.status == StepStatus.SUCCESS]
        failed_steps = [name for name, step in self.results.items() 
                       if step.status == StepStatus.FAILED]
        
        report = {
            "pipeline_summary": {
                "start_time": self.pipeline_start_time.isoformat() if self.pipeline_start_time else None,
                "end_time": self.pipeline_end_time.isoformat() if self.pipeline_end_time else None,
                "total_duration_seconds": (self.pipeline_end_time - self.pipeline_start_time).total_seconds() if self.pipeline_end_time and self.pipeline_start_time else None,
                "total_records_processed": total_records,
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "successful_steps": len(successful_steps),
                "failed_steps": len(failed_steps),
                "success_rate": len(successful_steps) / len(self.pipeline_steps) * 100
            },
            "step_details": {
                name: {
                    "status": step.status.value,
                    "start_time": step.start_time.isoformat() if step.start_time else None,
                    "end_time": step.end_time.isoformat() if step.end_time else None,
                    "duration_seconds": step.duration_seconds,
                    "records_processed": step.records_processed,
                    "errors": step.errors,
                    "warnings": step.warnings,
                    "details": step.details
                }
                for name, step in self.results.items()
            },
            "failed_steps_summary": failed_steps,
            "recommendations": self._generate_recommendations()
        }
        
        return report
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on monitoring results"""
        recommendations = []
        
        for name, step in self.results.items():
            if step.status == StepStatus.FAILED:
                if name == "alpha_vantage_calls":
                    recommendations.append("Check AlphaVantage API key and rate limits")
                elif name == "portfolio_snapshots":
                    recommendations.append("Verify database connectivity and user portfolio data")
                elif name == "leaderboard_calculation":
                    recommendations.append("Check leaderboard calculation logic and data availability")
                elif name == "html_prerendering":
                    recommendations.append("Verify template rendering and database schema")
                elif name == "chart_generation":
                    recommendations.append("Check chart data availability and rendering logic")
            
            if step.duration_seconds and step.duration_seconds > 300:  # 5 minutes
                recommendations.append(f"Step '{name}' took {step.duration_seconds:.1f}s - consider optimization")
        
        return recommendations

def create_monitoring_endpoint():
    """Create Flask endpoint for monitoring market close pipeline"""
    endpoint_code = '''
@app.route('/admin/market-close-status')
@login_required
def admin_market_close_status():
    """Monitor the status of market close pipeline processes"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, LeaderboardCache, UserPortfolioChartCache
        import json
        
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Check portfolio snapshots
        snapshots_today = PortfolioSnapshot.query.filter_by(date=today).count()
        snapshots_yesterday = PortfolioSnapshot.query.filter_by(date=yesterday).count()
        
        # Check leaderboard cache
        leaderboard_entries = LeaderboardCache.query.count()
        recent_leaderboard = LeaderboardCache.query.filter(
            LeaderboardCache.generated_at >= datetime.now() - timedelta(hours=24)
        ).count()
        
        # Check chart cache
        chart_entries = UserPortfolioChartCache.query.count()
        recent_charts = UserPortfolioChartCache.query.filter(
            UserPortfolioChartCache.generated_at >= datetime.now() - timedelta(hours=24)
        ).count()
        
        # Check for HTML pre-rendering
        html_prerendered = 0
        try:
            html_entries = LeaderboardCache.query.filter(
                LeaderboardCache.rendered_html.isnot(None),
                LeaderboardCache.generated_at >= datetime.now() - timedelta(hours=24)
            ).count()
            html_prerendered = html_entries
        except Exception:
            html_prerendered = 0
        
        # Determine overall status
        pipeline_health = "healthy"
        issues = []
        
        if snapshots_today == 0:
            pipeline_health = "warning"
            issues.append("No portfolio snapshots created today")
        
        if recent_leaderboard == 0:
            pipeline_health = "warning" 
            issues.append("No recent leaderboard updates (last 24h)")
        
        if recent_charts == 0:
            pipeline_health = "warning"
            issues.append("No recent chart generation (last 24h)")
        
        return jsonify({
            "success": True,
            "pipeline_health": pipeline_health,
            "timestamp": datetime.now().isoformat(),
            "daily_snapshots": {
                "today": snapshots_today,
                "yesterday": snapshots_yesterday
            },
            "leaderboard_cache": {
                "total_entries": leaderboard_entries,
                "recent_updates": recent_leaderboard,
                "html_prerendered": html_prerendered
            },
            "chart_cache": {
                "total_entries": chart_entries,
                "recent_generation": recent_charts
            },
            "issues": issues,
            "next_market_close": "5:00 PM ET (9:00 PM UTC) on weekdays"
        })
        
    except Exception as e:
        logger.error(f"Market close status check error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/admin/trigger-market-close-test', methods=['POST'])
@login_required  
def admin_trigger_market_close_test():
    """Manually trigger market close pipeline for testing"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from market_close_monitor import MarketCloseMonitor
        
        monitor = MarketCloseMonitor()
        monitor.start_pipeline()
        
        # Test each component
        results = {}
        
        # 1. Test portfolio snapshots
        monitor.start_step("portfolio_snapshots")
        try:
            from portfolio_performance import PortfolioPerformanceCalculator
            calculator = PortfolioPerformanceCalculator()
            
            # Test with a few users
            from models import User
            test_users = User.query.limit(3).all()
            snapshot_count = 0
            
            for user in test_users:
                try:
                    calculator.create_daily_snapshot(user.id)
                    snapshot_count += 1
                except Exception as e:
                    monitor.results["portfolio_snapshots"].errors.append(f"User {user.id}: {str(e)}")
            
            monitor.complete_step("portfolio_snapshots", True, snapshot_count)
            
        except Exception as e:
            monitor.complete_step("portfolio_snapshots", False, 0, [str(e)])
        
        # 2. Test leaderboard calculation
        monitor.start_step("leaderboard_calculation")
        try:
            from leaderboard_utils import update_leaderboard_cache
            
            # Test with just 7D period
            updated_count = update_leaderboard_cache(periods=['7D'])
            monitor.complete_step("leaderboard_calculation", True, updated_count)
            
        except Exception as e:
            monitor.complete_step("leaderboard_calculation", False, 0, [str(e)])
        
        # 3. Test HTML pre-rendering (check if it worked)
        monitor.start_step("html_prerendering")
        try:
            from models import LeaderboardCache
            html_count = LeaderboardCache.query.filter(
                LeaderboardCache.rendered_html.isnot(None)
            ).count()
            
            if html_count > 0:
                monitor.complete_step("html_prerendering", True, html_count)
            else:
                monitor.complete_step("html_prerendering", False, 0, 
                                    ["No HTML pre-rendering found - may need cron job run"])
            
        except Exception as e:
            monitor.complete_step("html_prerendering", False, 0, [str(e)])
        
        report = monitor.end_pipeline()
        
        return jsonify({
            "success": True,
            "message": "Market close test completed",
            "report": report
        })
        
    except Exception as e:
        logger.error(f"Market close test error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
'''
    
    return endpoint_code

if __name__ == "__main__":
    # Example usage
    monitor = MarketCloseMonitor()
    monitor.start_pipeline()
    
    # Simulate steps
    monitor.start_step("alpha_vantage_calls")
    monitor.complete_step("alpha_vantage_calls", True, 150, warnings=["Rate limit approaching"])
    
    monitor.start_step("portfolio_snapshots")
    monitor.complete_step("portfolio_snapshots", True, 25)
    
    monitor.start_step("leaderboard_calculation") 
    monitor.complete_step("leaderboard_calculation", False, 0, ["Database connection timeout"])
    
    report = monitor.end_pipeline()
    print("\n" + "="*80)
    print("FINAL REPORT:")
    print(json.dumps(report, indent=2))
