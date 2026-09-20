"""One Bedrock call from a laptop. No Lambda, no SAM, no app code.

Run it to prove three things in order:
  1. boto3 has credentials and they work.
  2. Some Claude model is actually enabled for your account in this region.
  3. A round trip returns text.

It does not hardcode a model id. Which Claude models exist in a region, and
whether they are callable directly or only through an inference profile,
depends on the region and on what your account has been granted. The script
asks Bedrock and prints what it finds.

    python scratch/test_bedrock.py --list
    python scratch/test_bedrock.py
    python scratch/test_bedrock.py --model-id apac.anthropic.claude-...
    python scratch/test_bedrock.py --region us-east-1
"""

from __future__ import annotations

import argparse
import sys

try:
    import boto3
    from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
except ImportError:
    sys.exit("boto3 is not installed. Run: pip install boto3")

DEFAULT_REGION = "ap-south-1"

# Order to try when nothing is passed to --model-id. Matched as substrings
# against whatever ids your account actually exposes, so an entry that does
# not exist in your region is simply skipped.
PREFERRED_MODELS = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5",
    "claude-opus-4-8",
    "claude-sonnet-4-6",
)
PROMPT = "Reply with exactly the words: bedrock is working."


def whoami(region: str) -> None:
    """Confirm credentials resolve before touching Bedrock at all."""
    ident = boto3.client("sts", region_name=region).get_caller_identity()
    print(f"account {ident['Account']}  arn {ident['Arn']}")


def discover(region: str) -> tuple[list[dict], list[dict]]:
    """Ask the Bedrock control plane what Claude models this account can see."""
    bedrock = boto3.client("bedrock", region_name=region)

    models = [
        m for m in bedrock.list_foundation_models(byProvider="anthropic").get("modelSummaries", [])
        if "claude" in m.get("modelId", "").lower()
    ]

    profiles = []
    for p in bedrock.list_inference_profiles().get("inferenceProfileSummaries", []):
        if "claude" in p.get("inferenceProfileId", "").lower():
            profiles.append(p)

    return models, profiles


def show(models: list[dict], profiles: list[dict]) -> None:
    print("\nFoundation models (direct ids):")
    if not models:
        print("  none visible - either no Anthropic models in this region, or no access granted")
    for m in models:
        types = ",".join(m.get("inferenceTypesSupported") or []) or "-"
        print(f"  {m['modelId']}\n      name={m.get('modelName')} inference={types}")

    print("\nInference profiles (use these when a model refuses on-demand calls):")
    if not profiles:
        print("  none visible")
    for p in profiles:
        print(f"  {p['inferenceProfileId']}\n      name={p.get('inferenceProfileName')} status={p.get('status')}")


def choose(models: list[dict], profiles: list[dict]) -> str | None:
    """Prefer an inference profile. Newer Claude models on Bedrock are commonly
    callable only through one, and a profile id also works where a direct id does."""
    active = [p for p in profiles if p.get("status", "ACTIVE") == "ACTIVE"]
    if active:
        # Newest first, otherwise the oldest profile in the list wins by accident.
        def rank(profile: dict) -> int:
            pid = profile["inferenceProfileId"]
            for i, name in enumerate(PREFERRED_MODELS):
                if name in pid:
                    return i
            return len(PREFERRED_MODELS)

        return sorted(active, key=rank)[0]["inferenceProfileId"]
    on_demand = [m for m in models if "ON_DEMAND" in (m.get("inferenceTypesSupported") or [])]
    if on_demand:
        return on_demand[0]["modelId"]
    return models[0]["modelId"] if models else None


def call(region: str, model_id: str) -> None:
    """Use the Converse API. It takes the same message shape for every provider,
    so there is no Anthropic-specific request body to get wrong."""
    runtime = boto3.client("bedrock-runtime", region_name=region)
    response = runtime.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": PROMPT}]}],
        inferenceConfig={"maxTokens": 100, "temperature": 0},
    )
    try:
        text = response["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError):
        print("Unexpected response shape. Raw response follows:")
        print(response)
        raise
    usage = response.get("usage", {})
    print(f"\nmodel replied: {text.strip()}")
    print(f"tokens in={usage.get('inputTokens')} out={usage.get('outputTokens')}")


def explain(exc: ClientError, region: str, model_id: str | None) -> None:
    """Translate the Bedrock errors you will hit on a first run."""
    code = exc.response.get("Error", {}).get("Code", "")
    message = exc.response.get("Error", {}).get("Message", "")
    print(f"\n{code}: {message}\n", file=sys.stderr)

    if code == "AccessDeniedException" and "being verified" in message.lower():
        print(
            "Nothing is wrong with your code or your IAM policy.\n"
            "  AWS verifies new accounts before allowing model invocation. It usually\n"
            "  clears in under 2 hours. Listing models works before invoking does.\n"
            "  Re-run this exact command later; no change is needed.",
            file=sys.stderr,
        )
    elif code == "AccessDeniedException" and "model" in message.lower():
        print(
            "Model access has not been granted in this region.\n"
            f"  Bedrock console -> region {region} -> Model access -> Modify model access\n"
            "  Tick the Anthropic Claude models and submit. Approval is usually immediate.\n"
            "  Access is PER REGION. Granting it in us-east-1 does nothing for ap-south-1.",
            file=sys.stderr,
        )
    elif code == "AccessDeniedException":
        print(
            "Your IAM identity is missing a Bedrock permission.\n"
            "  Needed here: bedrock:ListFoundationModels, bedrock:ListInferenceProfiles,\n"
            "  bedrock:InvokeModel, and sts:GetCallerIdentity.",
            file=sys.stderr,
        )
    elif code == "ValidationException" and "on-demand" in message.lower():
        print(
            "This model cannot be called by its bare model id. It needs an inference profile.\n"
            "  Run with --list and pass an inference profile id to --model-id instead.",
            file=sys.stderr,
        )
    elif code == "ResourceNotFoundException":
        print(
            f"No such model in {region}. Either the id is wrong or the model does not exist\n"
            "  in this region. Run --list to see what is actually there.",
            file=sys.stderr,
        )
    elif code == "ThrottlingException":
        print("Rate limited. Wait and retry. New accounts have low Bedrock quotas.", file=sys.stderr)
    elif code in ("UnrecognizedClientException", "InvalidSignatureException"):
        print("Credentials are present but invalid. Re-run: aws configure", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke test one Bedrock call.")
    ap.add_argument("--region", default=DEFAULT_REGION)
    ap.add_argument("--model-id", help="skip discovery and call this id directly")
    ap.add_argument("--list", action="store_true", help="discover and print, do not call")
    args = ap.parse_args()

    model_id = args.model_id
    try:
        whoami(args.region)

        if not model_id or args.list:
            models, profiles = discover(args.region)
            show(models, profiles)
            if args.list:
                return 0
            model_id = choose(models, profiles)
            if not model_id:
                print(
                    f"\nNo Claude model is available to this account in {args.region}.\n"
                    "Grant model access in the Bedrock console, or try --region us-east-1.",
                    file=sys.stderr,
                )
                return 1
            print(f"\nchose {model_id}  (override with --model-id)")

        call(args.region, model_id)
        return 0

    except NoCredentialsError:
        print("No AWS credentials found. Run: aws configure", file=sys.stderr)
        return 1
    except EndpointConnectionError as exc:
        print(f"Cannot reach the endpoint. Is {args.region!r} a real region?\n{exc}", file=sys.stderr)
        return 1
    except ClientError as exc:
        explain(exc, args.region, model_id)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
