#!/usr/bin/env python3
"""
UFRO Orquestador MCP Server

Provides Model Context Protocol tools for LLM systems to interact with:
- PP2 Identity Verification services
- PP1 UFRO Normativa chatbot
- Analytics and metrics

Tools provided:
- identify_person: Verify identity from image
- ask_normativa: Query UFRO normativa
- identify_and_answer: Combined identity verification + normativa query
- get_metrics: Retrieve usage analytics
"""

import asyncio
import json
import os
import sys
import logging
import base64
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import aiohttp
import yaml

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8001"))


class UFROOrquestradorMCP:
    """MCP Server for UFRO Orquestrador"""

    def __init__(self):
        self.server = Server("ufro-orquestador")
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize_http_session(self):
        """Initialize HTTP session for API calls"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close_http_session(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def call_api(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP call to the UFRO Orquestador API"""
        await self.initialize_http_session()

        url = f"{API_BASE_URL}{endpoint}"

        try:
            async with self.session.request(method, url, **kwargs) as response:
                if response.content_type == 'application/json':
                    data = await response.json()
                else:
                    text = await response.text()
                    data = {"text": text, "status_code": response.status}

                if response.status >= 400:
                    raise aiohttp.ClientError(
                        f"HTTP {response.status}: {data}")

                return data

        except Exception as e:
            logger.error(f"API call failed: {method} {url} - {e}")
            raise

    def setup_tools(self):
        """Setup MCP tools"""

        @self.server.call_tool()
        async def identify_person(image_data: str, image_format: str = "jpeg") -> List[Union[TextContent, ImageContent]]:
            """
            Identify a person from an image using PP2 services

            Args:
                image_data: Base64 encoded image data
                image_format: Image format (jpeg/png)

            Returns:
                Identity verification results
            """
            try:
                try:
                    image_bytes = base64.b64decode(image_data)
                except Exception as e:
                    return [TextContent(type="text", text=f"Error decoding image: {e}")]

                data = aiohttp.FormData()
                data.add_field('image',
                               image_bytes,
                               filename=f"image.{image_format}",
                               content_type=f"image/{image_format}")

                result = await self.call_api("POST", "/identify-and-answer", data=data)

                decision = result.get("decision", "unknown")
                identity = result.get("identity")
                candidates = result.get("candidates", [])
                timing = result.get("timing_ms", 0)

                response_text = f"🔍 **Identity Verification Result**\n\n"
                response_text += f"**Decision:** {decision.upper()}\n"
                response_text += f"**Processing Time:** {timing}ms\n\n"

                if identity:
                    response_text += f"**Identified Person:**\n"
                    response_text += f"- Name: {identity.get('name', 'N/A')}\n"
                    response_text += f"- Confidence: {
                        identity.get('score', 0):.2f}\n\n"

                if candidates:
                    response_text += f"**Alternative Candidates:** ({
                        len(candidates)})\n"
                    for i, candidate in enumerate(candidates[:3], 1):
                        response_text += f"{i}. {candidate.get('name', 'N/A')} (score: {
                            candidate.get('score', 0):.2f})\n"

                return [TextContent(type="text", text=response_text)]

            except Exception as e:
                logger.error(f"Error in identify_person: {e}")
                return [TextContent(type="text", text=f"❌ Error identifying person: {e}")]

        @self.server.call_tool()
        async def ask_normativa(question: str) -> List[TextContent]:
            """
            Ask a question about UFRO normativa using PP1 chatbot

            Args:
                question: Question about UFRO academic regulations

            Returns:
                Answer from the normativa chatbot
            """
            try:
                data = aiohttp.FormData()
                data.add_field('question', question)

                result = await self.call_api("POST", "/identify-and-answer", data=data)

                normativa_answer = result.get("normativa_answer")
                timing = result.get("timing_ms", 0)

                if not normativa_answer:
                    response_text = "⚠️ **No answer available**\n\n"
                    response_text += "The PP1 normativa service did not return an answer. "
                    response_text += "This could be because:\n"
                    response_text += "- The service is temporarily unavailable\n"
                    response_text += "- The question is outside the knowledge domain\n"
                    response_text += f"- Service timeout (processing took {
                        timing}ms)\n"
                else:
                    response_text = f"📚 **UFRO Normativa Answer**\n\n"
                    response_text += f"**Question:** {question}\n\n"
                    response_text += f"**Answer:** {
                        normativa_answer.get('answer', 'No answer provided')}\n\n"

                    sources = normativa_answer.get('sources', [])
                    if sources:
                        response_text += f"**Sources:** {
                            ', '.join(sources)}\n\n"

                    response_text += f"**Processing Time:** {timing}ms\n"

                return [TextContent(type="text", text=response_text)]

            except Exception as e:
                logger.error(f"Error in ask_normativa: {e}")
                return [TextContent(type="text", text=f"❌ Error querying normativa: {e}")]

        @self.server.call_tool()
        async def identify_and_answer(image_data: str, question: str, image_format: str = "jpeg") -> List[TextContent]:
            """
            Combined tool: Identify person from image AND answer normativa question

            Args:
                image_data: Base64 encoded image data
                question: Question about UFRO academic regulations
                image_format: Image format (jpeg/png)

            Returns:
                Combined identity verification and normativa answer results
            """
            try:
                try:
                    image_bytes = base64.b64decode(image_data)
                except Exception as e:
                    return [TextContent(type="text", text=f"Error decoding image: {e}")]

                data = aiohttp.FormData()
                data.add_field('image',
                               image_bytes,
                               filename=f"image.{image_format}",
                               content_type=f"image/{image_format}")
                data.add_field('question', question)

                result = await self.call_api("POST", "/identify-and-answer", data=data)

                decision = result.get("decision", "unknown")
                identity = result.get("identity")
                candidates = result.get("candidates", [])
                normativa_answer = result.get("normativa_answer")
                timing = result.get("timing_ms", 0)
                request_id = result.get("request_id", "N/A")

                response_text = f"🎯 **UFRO Orquestador - Complete Analysis**\n\n"
                response_text += f"**Request ID:** {request_id}\n"
                response_text += f"**Total Processing Time:** {timing}ms\n\n"

                response_text += f"## 🔍 Identity Verification\n"
                response_text += f"**Decision:** {decision.upper()}\n"

                if identity:
                    response_text += f"**Identified:** {identity.get('name', 'N/A')} (confidence: {
                        identity.get('score', 0):.2f})\n"

                if candidates:
                    response_text += f"**Alternatives:** {
                        len(candidates)} candidates found\n"

                response_text += "\n"

                response_text += f"## 📚 Normativa Answer\n"
                response_text += f"**Question:** {question}\n\n"

                if normativa_answer:
                    response_text += f"**Answer:** {
                        normativa_answer.get('answer', 'No answer provided')}\n"

                    sources = normativa_answer.get('sources', [])
                    if sources:
                        response_text += f"**Sources:** {', '.join(sources)}\n"
                else:
                    response_text += "⚠️ **No normativa answer available** (service may be unavailable)\n"

                return [TextContent(type="text", text=response_text)]

            except Exception as e:
                logger.error(f"Error in identify_and_answer: {e}")
                return [TextContent(type="text", text=f"❌ Error in combined operation: {e}")]

        @self.server.call_tool()
        async def get_metrics(metric_type: str = "summary", days: int = 7) -> List[TextContent]:
            """
            Get analytics and metrics from the UFRO Orquestador

            Args:
                metric_type: Type of metrics (summary/by-user-type/decisions/services/volume/pp2-timeouts)
                days: Number of days to analyze (1-30)

            Returns:
                Formatted metrics report
            """
            try:
                if days < 1 or days > 30:
                    days = 7

                valid_types = ["summary", "by-user-type",
                               "decisions", "services", "volume", "pp2-timeouts"]
                if metric_type not in valid_types:
                    metric_type = "summary"

                endpoint = f"/metrics/{metric_type}?days={days}"
                result = await self.call_api("GET", endpoint)

                if not result.get("success"):
                    return [TextContent(type="text", text="❌ Failed to retrieve metrics")]

                data = result.get("data", {})

                response_text = f"📊 **UFRO Orquestador Metrics** ({d
                                                                   days} days)\n\n"

                if metric_type == "summary":
                    response_text += f"**Total Requests:** {
                        data.get('total_requests', 0):,}\n"
                    response_text += f"**Average Response Time:** {
                        data.get('avg_timing_ms', 0):.1f}ms\n"
                    response_text += f"**Success Rate:** {
                        data.get('success_rate', 0):.1f}%\n"
                    response_text += f"**PP1 Usage:** {
                        data.get('pp1_usage_rate', 0):.1f}%\n"
                    response_text += f"**Unique Users:** {
                        data.get('unique_users', 0):,}\n"

                elif metric_type == "decisions":
                    response_text += "**Identity Decision Breakdown:**\n"
                    for decision in data:
                        count = decision.get('count', 0)
                        rate = decision.get('rate', 0)
                        response_text += f"- {decision.get('decision', 'Unknown').upper()}: {
                            count:,} ({rate:.1f}%)\n"

                elif metric_type == "services":
                    pp2_data = data.get('pp2_services', {})
                    pp1_data = data.get('pp1_service', {})

                    response_text += "**PP2 Services:**\n"
                    response_text += f"- Avg Response Time: {
                        pp2_data.get('avg_timing_ms', 0):.1f}ms\n"
                    response_text += f"- Timeout Rate: {
                        pp2_data.get('timeout_rate', 0):.1f}%\n\n"

                    response_text += "**PP1 Service:**\n"
                    response_text += f"- Usage Rate: {
                        pp1_data.get('usage_rate', 0):.1f}%\n"
                    response_text += f"- Avg Response Time: {
                        pp1_data.get('avg_timing_ms', 0):.1f}ms\n"

                elif metric_type == "volume":
                    response_text += "**Hourly Request Volume:**\n"
                    for hour_data in data[-24:]:
                        hour = hour_data.get('hour', 0)
                        count = hour_data.get('count', 0)
                        response_text += f"- Hour {
                            hour:02d}: {count} requests\n"

                else:
                    response_text += f"**{metric_type.replace(
                        '-', ' ').title()} Data:**\n"
                    response_text += json.dumps(data,
                                                indent=2, ensure_ascii=False)

                return [TextContent(type="text", text=response_text)]

            except Exception as e:
                logger.error(f"Error in get_metrics: {e}")
                return [TextContent(type="text", text=f"❌ Error retrieving metrics: {e}")]

        @self.server.call_tool()
        async def health_check() -> List[TextContent]:
            """
            Check the health status of all UFRO Orquestador services

            Returns:
                Health status report
            """
            try:
                result = await self.call_api("GET", "/healthz")

                status = result.get("status", "unknown")
                mongodb_ok = result.get("mongodb_connected", False)
                pp1_available = result.get("pp1_available", False)
                pp2_count = result.get("pp2_services_count", 0)
                timestamp = result.get("timestamp", "")

                response_text = f"🏥 **UFRO Orquestador Health Check**\n\n"
                response_text += f"**Overall Status:** {status.upper()}\n"
                response_text += f"**Timestamp:** {timestamp}\n\n"

                response_text += f"**Services:**\n"
                response_text += f"- MongoDB: {
                    '✅ Connected' if mongodb_ok else '❌ Disconnected'}\n"
                response_text += f"- PP1 Normativa: {
                    '✅ Available' if pp1_available else '⚠️ Unavailable'}\n"
                response_text += f"- PP2 Identity: {
                    pp2_count} service(s) active\n\n"

                if status != "healthy":
                    response_text += "⚠️ **Warning:** Some services may be experiencing issues. "
                    response_text += "Check individual service logs for more details.\n"

                return [TextContent(type="text", text=response_text)]

            except Exception as e:
                logger.error(f"Error in health_check: {e}")
                return [TextContent(type="text", text=f"❌ Error checking health: {e}")]

    def setup_handlers(self):
        """Setup MCP server event handlers"""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available MCP tools"""
            return [
                Tool(
                    name="identify_person",
                    description="Identify a person from an image using PP2 verification services",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "image_data": {
                                "type": "string",
                                "description": "Base64 encoded image data"
                            },
                            "image_format": {
                                "type": "string",
                                "enum": ["jpeg", "png"],
                                "default": "jpeg",
                                "description": "Image format"
                            }
                        },
                        "required": ["image_data"]
                    }
                ),
                Tool(
                    name="ask_normativa",
                    description="Ask questions about UFRO academic regulations using PP1 chatbot",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "Question about UFRO academic regulations, policies, or procedures"
                            }
                        },
                        "required": ["question"]
                    }
                ),
                Tool(
                    name="identify_and_answer",
                    description="Combined operation: identify person from image AND answer normativa question",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "image_data": {
                                "type": "string",
                                "description": "Base64 encoded image data"
                            },
                            "question": {
                                "type": "string",
                                "description": "Question about UFRO academic regulations"
                            },
                            "image_format": {
                                "type": "string",
                                "enum": ["jpeg", "png"],
                                "default": "jpeg",
                                "description": "Image format"
                            }
                        },
                        "required": ["image_data", "question"]
                    }
                ),
                Tool(
                    name="get_metrics",
                    description="Retrieve analytics and usage metrics from the UFRO Orquestador",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "metric_type": {
                                "type": "string",
                                "enum": ["summary", "by-user-type", "decisions", "services", "volume", "pp2-timeouts"],
                                "default": "summary",
                                "description": "Type of metrics to retrieve"
                            },
                            "days": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 30,
                                "default": 7,
                                "description": "Number of days to analyze"
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="health_check",
                    description="Check the health status of all UFRO Orquestador services",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                )
            ]

    async def run(self):
        """Run the MCP server"""
        self.setup_tools()
        self.setup_handlers()

        import mcp.server.stdio
        async with mcp.server.stdio.stdio_server() as streams:
            await self.server.run(streams)


async def main():
    """Main entry point"""
    logger.info(f"Starting UFRO Orquestrador MCP Server on port {
                MCP_SERVER_PORT}")
    logger.info(f"Connecting to API at: {API_BASE_URL}")

    server = UFROOrquestradorMCP()

    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("MCP Server interrupted by user")
    except Exception as e:
        logger.error(f"MCP Server error: {e}", exc_info=True)
    finally:
        await server.close_http_session()
        logger.info("MCP Server shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
