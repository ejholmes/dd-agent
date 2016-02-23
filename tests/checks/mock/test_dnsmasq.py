from tests.checks.common import AgentCheckTest

def mock_config():
    return {'init_config': {}, 'instances': [{}]}

def mock_query_txt(name):
    return '"10"'

class TestCheckDnsmasq(AgentCheckTest):
    CHECK_NAME = 'dnsmasq'

    def test_ok(self):
        self.run_check(mock_config(), mocks={'query_txt': mock_query_txt})
        self.assertMetric('dnsmasq.cachesize', value=10)
        self.assertMetric('dnsmasq.insertions', value=10)
        self.assertMetric('dnsmasq.evictions', value=10)
        self.assertMetric('dnsmasq.misses', value=10)
        self.assertMetric('dnsmasq.hits', value=10)
