from flask import Flask, request, jsonify

app = Flask(__name__)

# -------------------------------
# Tool Implementations
# -------------------------------

def get_account_holder(input_str: str) -> str:
    # TODO - enable this once multi-turn conversation is supported.
    # Requires a different model to avoid RPM violations.
    return ""

def get_account_number(name: str) -> str:
    name = name.lower()

    if name == "michael":
        return "123456"
    elif name == "mary":
        return "789012"
    return "0"

def get_account_balance(account_number: str) -> str:
    if account_number == "123456":
        return "1500.00"
    elif account_number == "789012":
        return "150.00"
    return "0.00"

def get_account_address(account_number: str) -> str:
    if account_number == "123456":
        return "123 Sesame Street Suite 1, New York, NY 55555"
    elif account_number == "789012":
        return "123 Sesame Street Suite 2, New York, NY 55555"
    return ""

def send_new_card(address: str) -> str:
    return "false" if not address.strip() else "true"


# -------------------------------
# JSON-RPC Endpoint
# -------------------------------

@app.route("/mcp", methods=["POST"])
def mcp_endpoint():
    # Handles JSON-RPC 2.0 requests from the agent.
    # Expected request format:
    # {
    #     "jsonrpc": "2.0",
    #     "method": "<ToolName>",
    #     "params": {"input": "<argument>"},
    #     "id": "1"
    # }
    try:
        data = request.get_json(force=True)
        method = data.get("method")
        params = data.get("params", {})
        arg = params.get("input", "")

        # Map method names to tool functions
        tools = {
            "GetAccountHolder": get_account_holder,
            "GetAccountNumber": get_account_number,
            "GetAccountBalance": get_account_balance,
            "GetAccountAddress": get_account_address,
            "SendNewCard": send_new_card
        }

        if method not in tools:
            return jsonify({
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "error": {"code": -32601, "message": f"Unknown method: {method}"}
            })

        # Call the tool function
        result = tools[method](arg)

        return jsonify({
            "jsonrpc": "2.0",
            "id": data.get("id"),
            "result": result
        })

    except Exception as e:
        return jsonify({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32603, "message": str(e)}
        })


# -------------------------------
# Entry Point
# -------------------------------

if __name__ == "__main__":
    # Run the MCP server on localhost:5000
    print("MCP server running at http://localhost:5000/mcp")
    app.run(host="0.0.0.0", port=5000)