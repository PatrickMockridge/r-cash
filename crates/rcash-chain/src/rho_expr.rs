//! Decoding the node's `RhoExpr` wire values.
//!
//! Since AUDIT C38 every arm wraps its payload in `{"data": …}`:
//! `{"ExprInt":{"data":42}}`, `{"ExprString":{"data":"NGN"}}`,
//! `{"ExprTuple":{"data":[…]}}`, `{"ExprMap":{"data":{"key": expr}}}`.
//! The decoder accepts that shape and the older bare shape, because the node
//! documents clients accepting both.

use std::collections::BTreeMap;

use serde_json::Value;

use crate::error::ChainError;

/// A decoded Rholang value.
#[derive(Clone, Debug, PartialEq)]
pub enum RhoValue {
    Par(Vec<RhoValue>),
    Tuple(Vec<RhoValue>),
    List(Vec<RhoValue>),
    Set(Vec<RhoValue>),
    Map(BTreeMap<String, RhoValue>),
    Bool(bool),
    Int(i64),
    Str(String),
    Uri(String),
    /// Hex of the byte array.
    Bytes(String),
    Unforg {
        kind: String,
        hex: String,
    },
}

impl RhoValue {
    /// Decode one wire value.
    pub fn decode(value: &Value) -> Result<Self, ChainError> {
        let object = value
            .as_object()
            .ok_or_else(|| ChainError::Decode(format!("not a RhoExpr: {value}")))?;
        if object.len() != 1 {
            return Err(ChainError::Decode(format!(
                "RhoExpr has {} arms: {value}",
                object.len()
            )));
        }
        let (tag, payload) = object.iter().next().expect("one arm");
        let data = payload.get("data").unwrap_or(payload);
        match tag.as_str() {
            "ExprInt" => Ok(Self::Int(data.as_i64().ok_or_else(|| {
                ChainError::Decode(format!("ExprInt is not i64: {data}"))
            })?)),
            "ExprBool" => {
                Ok(Self::Bool(data.as_bool().ok_or_else(|| {
                    ChainError::Decode(format!("ExprBool: {data}"))
                })?))
            }
            "ExprString" => Ok(Self::Str(expect_str(data, "ExprString")?)),
            "ExprUri" => Ok(Self::Uri(expect_str(data, "ExprUri")?)),
            "ExprBytes" => Ok(Self::Bytes(expect_str(data, "ExprBytes")?)),
            "ExprPar" => Ok(Self::Par(decode_many(data)?)),
            "ExprTuple" => Ok(Self::Tuple(decode_many(data)?)),
            "ExprList" => Ok(Self::List(decode_many(data)?)),
            "ExprSet" => Ok(Self::Set(decode_many(data)?)),
            "ExprMap" => {
                let map = data
                    .as_object()
                    .ok_or_else(|| ChainError::Decode(format!("ExprMap: {data}")))?;
                let mut out = BTreeMap::new();
                for (key, value) in map {
                    out.insert(key.clone(), Self::decode(value)?);
                }
                Ok(Self::Map(out))
            }
            "ExprUnforg" => {
                let unforg = data
                    .as_object()
                    .ok_or_else(|| ChainError::Decode(format!("ExprUnforg: {data}")))?;
                let (kind, inner) = unforg
                    .iter()
                    .next()
                    .ok_or_else(|| ChainError::Decode("empty unforgable".into()))?;
                let hex = inner
                    .get("data")
                    .and_then(Value::as_str)
                    .ok_or_else(|| ChainError::Decode(format!("unforgable {kind}: {inner}")))?;
                Ok(Self::Unforg {
                    kind: kind.clone(),
                    hex: hex.to_string(),
                })
            }
            other => Err(ChainError::Decode(format!("unknown RhoExpr arm {other}"))),
        }
    }

    pub fn as_int(&self) -> Option<i64> {
        match self {
            Self::Int(n) => Some(*n),
            _ => None,
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Self::Bool(b) => Some(*b),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Self::Str(s) | Self::Uri(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_tuple(&self) -> Option<&[RhoValue]> {
        match self {
            Self::Tuple(items) | Self::Par(items) => Some(items),
            _ => None,
        }
    }

    pub fn as_list(&self) -> Option<&[RhoValue]> {
        match self {
            Self::List(items) | Self::Set(items) => Some(items),
            _ => None,
        }
    }

    pub fn as_map(&self) -> Option<&BTreeMap<String, RhoValue>> {
        match self {
            Self::Map(map) => Some(map),
            _ => None,
        }
    }

    /// Render as JSON for CLI and UI output. This is display only; it is not the wire
    /// format and must not be fed back to the node.
    pub fn to_json(&self) -> Value {
        let many = |items: &[RhoValue]| Value::Array(items.iter().map(RhoValue::to_json).collect());
        match self {
            Self::Par(items) | Self::Tuple(items) | Self::List(items) | Self::Set(items) => {
                many(items)
            }
            Self::Map(map) => Value::Object(
                map.iter()
                    .map(|(key, value)| (key.clone(), value.to_json()))
                    .collect(),
            ),
            Self::Bool(value) => Value::Bool(*value),
            Self::Int(value) => Value::from(*value),
            Self::Str(value) | Self::Uri(value) | Self::Bytes(value) => Value::from(value.clone()),
            Self::Unforg { kind, hex } => serde_json::json!({
                "unforgable": kind,
                "hex": hex,
            }),
        }
    }
}

fn expect_str(data: &Value, arm: &str) -> Result<String, ChainError> {
    data.as_str()
        .map(str::to_string)
        .ok_or_else(|| ChainError::Decode(format!("{arm} is not a string: {data}")))
}

fn decode_many(data: &Value) -> Result<Vec<RhoValue>, ChainError> {
    data.as_array()
        .ok_or_else(|| ChainError::Decode(format!("expected an array: {data}")))?
        .iter()
        .map(RhoValue::decode)
        .collect()
}

/// A protocol reply: `(true, …)` or `(false, reason)`.
#[derive(Clone, Debug, PartialEq)]
pub enum Reply {
    Ok(Vec<RhoValue>),
    Refused(String),
}

impl Reply {
    /// Parse a decoded value as the protocol's reply convention.
    pub fn from_value(value: &RhoValue) -> Result<Self, ChainError> {
        let items = value
            .as_tuple()
            .ok_or_else(|| ChainError::Decode(format!("reply is not a tuple: {value:?}")))?;
        let Some(first) = items.first() else {
            return Err(ChainError::Decode("empty reply tuple".into()));
        };
        match first.as_bool() {
            Some(true) => Ok(Self::Ok(items[1..].to_vec())),
            Some(false) => {
                let reason = items
                    .get(1)
                    .and_then(RhoValue::as_str)
                    .unwrap_or("refused")
                    .to_string();
                Ok(Self::Refused(reason))
            }
            None => Err(ChainError::Decode(format!(
                "reply tag is not a boolean: {first:?}"
            ))),
        }
    }

    /// The success payload, or the refusal reason.
    pub fn into_result(self) -> Result<Vec<RhoValue>, ChainError> {
        match self {
            Self::Ok(values) => Ok(values),
            Self::Refused(reason) => Err(ChainError::Refused(reason)),
        }
    }

    /// The first success value as an integer.
    pub fn int_at(&self, index: usize) -> Option<i64> {
        match self {
            Self::Ok(values) => values.get(index).and_then(RhoValue::as_int),
            Self::Refused(_) => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn decodes_the_enveloped_wire_shape() {
        let value = json!({"ExprTuple":{"data":[
            {"ExprBool":{"data":true}},
            {"ExprInt":{"data":42}},
            {"ExprString":{"data":"NGN"}}
        ]}});
        let decoded = RhoValue::decode(&value).unwrap();
        let items = decoded.as_tuple().unwrap();
        assert_eq!(items[0].as_bool(), Some(true));
        assert_eq!(items[1].as_int(), Some(42));
        assert_eq!(items[2].as_str(), Some("NGN"));
    }

    #[test]
    fn decodes_maps_and_lists() {
        let value = json!({"ExprMap":{"data":{
            "price": {"ExprInt":{"data":66666}},
            "fresh": {"ExprBool":{"data":false}}
        }}});
        let map = RhoValue::decode(&value).unwrap();
        assert_eq!(map.as_map().unwrap()["price"].as_int(), Some(66666));

        let list = json!({"ExprList":{"data":[{"ExprInt":{"data":1}},{"ExprInt":{"data":2}}]}});
        assert_eq!(RhoValue::decode(&list).unwrap().as_list().unwrap().len(), 2);
    }

    #[test]
    fn accepts_the_bare_legacy_shape() {
        let value = json!({"ExprInt":7});
        assert_eq!(RhoValue::decode(&value).unwrap().as_int(), Some(7));
    }

    #[test]
    fn replies_distinguish_success_from_refusal() {
        let ok = RhoValue::Tuple(vec![RhoValue::Bool(true), RhoValue::Int(3)]);
        assert_eq!(Reply::from_value(&ok).unwrap().int_at(0), Some(3));
        let no = RhoValue::Tuple(vec![RhoValue::Bool(false), RhoValue::Str("stale".into())]);
        assert_eq!(
            Reply::from_value(&no).unwrap(),
            Reply::Refused("stale".into())
        );
    }
}
